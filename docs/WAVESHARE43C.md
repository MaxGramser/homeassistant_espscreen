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
- The speaker, the microphone, the SD card slot and the clock chip on the board stay unused.

## Hardware references

- Waveshare's board support package for the 4.3C (Waveshare-ESP32-components, `bsp/esp32_s3_touch_lcd_4_3c`): its pin
  table, its timings and its use of the expander.
- [ESPHome Waveshare CH32V003 I/O Expander](https://esphome.io/components/waveshare_io_ch32v003/): the expander at
  I2C address 0x24, with eight lines, one PWM output and one ADC.
- [ESPHome MIPI RGB](https://esphome.io/components/display/mipi_rgb/). ESPHome's `ESP32-S3-TOUCH-LCD-4.3` model expects
  a CH422G, so the board file uses the `RPI` model (an RGB panel without an init sequence) with the 4.3's pins.
- I2C: SDA GPIO8, SCL GPIO9, shared by the GT911 and the expander. The GT911's interrupt line is GPIO4.
- Expander lines: EXIO1 touch reset, EXIO2 backlight enable, EXIO3 the speaker's amplifier (unused). The panel has no
  reset line.
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
6. Free internal heap with a full layout, any reset or I2C errors, and how long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
