# Waveshare ESP32-S3-Touch-LCD-4.3C, experimental

This is the **ESP32-S3-Touch-LCD-4.3C**, sold on its own and in the 4.3C-BOX: the 4.3-inch 800 x 480 IPS panel and
GT911 capacitive touch of the [Waveshare 4.3](EASY_SETUP.md), with 8 MB octal PSRAM and 16 MB flash. It is not the
ESP32-S3-Touch-LCD-4.3 without the "C": the 4.3C has Waveshare's CH32V003 expander (the one on the
[7B](WAVESHARE7B.md)) where the 4.3 has a CH422G. A 4.3C built as a 4.3 boots with a dark or stale screen and its log
says `touchscreen is marked FAILED: Calibration error`: the touch chip never leaves reset, because the expander that
holds its reset line is not the one the 4.3's board file drives. The board name is printed on the back, next to the
pin header: "ESP32-S3-Touch-LCD-4.3C". Physical acceptance has not been performed.

## Install

Update Tessera Screen Manager and choose the Waveshare ESP32-S3-Touch-LCD-4.3C (marked Experimental) in **New screen**. Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and
unique API/OTA keys. A 4.3C that was installed as a 4.3 keeps its name and keys: in its screen YAML, change the file of
the `display` package from `packages/waveshare43.yaml` to `packages/waveshare43c.yaml`, then install it once more.

The remote package is `packages/waveshare43c.yaml`; the checkout entry is `checkout/waveshare43c.yaml`. Both combine
`packages/core.yaml` with `packages/boards/waveshare43c.yaml`, which includes `packages/hardware/waveshare-ch32v003.yaml`,
the expander, touch and backlight it shares with the 7B. The board needs ESPHome 2026.7.0 or newer, the first release
with a component for its expander. Logs come over the USB-C cable, from the chip's own USB.

## Layout and capabilities

- Landscape: 800 x 480, three columns of three cells. Portrait: 480 x 800, one column of four cells. The same glass
  and grid as the 4.3.
- The backlight takes levels: brightness is a percentage, and standby, night mode, Sleep, Wake and the alert's flashes
  are enabled. The level is the expander's PWM output. Its enable line goes high once, at start, and never low again,
  so a dark standby is the darkest the PWM gives rather than a backlight switched off. The 4.3 browned out when it
  switched its backlight on from fully dark; this board never does that, but standby and the wake from it have not
  been seen on this hardware yet.
- Camera tiles, full-screen snapshots, live tile pictures, camera alerts and media artwork use the shared PSRAM
  implementation.
- GT911 reports pixel coordinates, with no resistive calibration. The existing touch filter and action guard remain in use.
- The speaker and the two microphones are supported (below, "Audio"); the SD card slot and the clock chip on the
  board stay unused.

## Audio

The board carries the Waveshare P4 panels' audio family (docs/P4_AUDIO.md): an **ES8311** codec at 0x18 for the
speaker (its ADC is not wired), an **ES7210** four-channel ADC at 0x40 with the board's two microphones on MIC1 and
MIC2, and an **NS4150B** amplifier. Both codecs sit on the board's only I2C bus (the touch bus). The speaker's output
feeds the ES7210's MIC3 through a divider (2.2 + 10 + 20 kOhm in series to a 4.3 kOhm differential shunt, 220 nF into
the ADC, about 24 dB down) as the echo cancellation's reference, and one I2S bus serves both codecs:

- I2S: MCLK GPIO6, BCLK GPIO44, LRCLK GPIO16, speaker data GPIO15 (to the ES8311), microphone data GPIO43 (from the
  ES7210) - Waveshare's own pin table (Waveshare-ESP32-components, `bsp/esp32_s3_touch_lcd_4_3c`).
- Amplifier: the NS4150B's enable is the CH32V003 expander's **EXIO3**, high for on, a 10 kOhm pull-down keeping it
  off at start. The firmware follows playback with it (300 ms after the last sound it goes dark again), so the
  amplifier neither pops when its clock starts nor hisses between sounds.

The transport is the P4 panels' **AEC by default** - full duplex on the one bus, the microphone and the reference
converted from 48 kHz to 16 kHz before the echo cancellation, so the screen listens while it speaks. The plain
half-duplex transport (ESPHome's own I2S bus, the microphone and the speaker taking turns, no AEC libraries in the
firmware) remains selectable: set `AUDIO_TRANSPORT: "i2s"` in the screen's Override YAML and rebuild. As on the P4
panels, the screen's Extras under Screen settings carry the volume, the microphone's switch, the microphone gain and
the automatic gain, and with the AEC transport the echo cancellation's switch and its status; the settings page of
the screen shows them as well. The default gain (30 dB) and the automatic gain (on) come from the parts; verify them
on the hardware.

This is a first implementation from the schematic, Waveshare's board support package and the P4 panels' proven
wiring; it has not been seen on the glass of a board here yet. If the reference's level is off - echo that is still
audible in the microphone, or a low voice next to a loud answer - the divider's exact attenuation is the place to
look: it changes the part's `AUDIO_REFERENCE_GAIN`, nothing in the transport.

## Hardware references

- Waveshare's board support package for the 4.3C (Waveshare-ESP32-components, `bsp/esp32_s3_touch_lcd_4_3c`): its pin
  table, its timings and its use of the expander.
- [ESPHome Waveshare CH32V003 I/O Expander](https://esphome.io/components/waveshare_io_ch32v003/): the expander at
  I2C address 0x24, with eight lines, one PWM output and one ADC.
- [ESPHome MIPI RGB](https://esphome.io/components/display/mipi_rgb/). ESPHome's `ESP32-S3-TOUCH-LCD-4.3` model expects
  a CH422G, so the board file uses the `RPI` model (an RGB panel without an init sequence) with the 4.3's pins.
- I2C: SDA GPIO8, SCL GPIO9, shared by the GT911 and the expander. The GT911's interrupt line is GPIO4.
- Expander lines: EXIO1 touch reset, EXIO2 backlight enable, EXIO3 the speaker's amplifier (the "Audio" section). The
  panel has no reset line.
- RGB: DE GPIO5, PCLK GPIO7, HSYNC GPIO46, VSYNC GPIO3, the 4.3's data pins, a 16 MHz pixel clock, porches of 8 and
  pulses of 4 (Waveshare's timing for this panel, the same the 4.3 uses).
- Backlight: the expander's PWM output, inverted, between the levels 1 and 247 that ESPHome gives for this expander.

## What to report while testing

1. Successful boot, appearance in Tessera, and the log's first lines: no `Calibration error`, and the bus scan finding
   the expander at 0x24 and the touch chip at 0x5D.
2. Correct colours and a stable picture across several page changes and cold starts. A picture that drifts sideways,
   flickers or has shifted colours points at the display block.
3. Physical taps near each corner, slider drags and edge swipes, lying down and standing up.
4. The brightness setting across its range, standby after the timeout and the wake by touch, several times in a row,
   and night mode. Report any restart, a dark screen that does not wake, or lost touch after a wake.
5. A full page of tiles, opening and closing the settings and detail cards.
6. Audio: an announcement and the media player through the speaker with clean onset and end; the microphone switch,
   gain and automatic gain through Home Assistant and the settings page, kept over a reboot; with the AEC transport,
   capture while an answer plays and the echo cancellation's switch and status. Any noise floor the microphone shows
   with the speaker silent.
7. Free internal heap with a full layout, any reset or I2C errors, and how long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
