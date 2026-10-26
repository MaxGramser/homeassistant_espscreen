# Waveshare ESP32-P4-NANO with the 10.1-DSI-TOUCH-A, experimental

This is the **two-piece** 10.1-inch combination: a Waveshare ESP32-P4 carrier board plus a separate
**10.1-DSI-TOUCH-A** panel (JD9365, 800 x 1280 IPS, GT911-compatible capacitive touch) on the MIPI-DSI FPC. It is not
the all-in-one [ESP32-P4-WIFI6-Touch-LCD-10.1](WAVESHARE101.md), which is one board with the same glass: the all-in-one
routes an LCD reset pin and a backlight PWM pin, and this carrier routes neither, so the two need different board
files. ESPHome names the panel after the Nano (`model: WAVESHARE-P4-NANO-10.1`), which is what the board is called
here. The ESP32-P4-NANO, the ESP32-P4-Module-DEV-KIT and the ESP32-P4-WIFI6-DEV-KIT carriers are wired the same for
the display, the touch bus and the panel's enable.

Tried on an ESP32-P4-Module-DEV-KIT with the 10.1-DSI-TOUCH-A, pre-v3 silicon (`chip revision: v1.3` in the boot log):
a cold start boots clean, and the panel, its rotation, the touch and the backlight were checked on the glass. The
ESP32-P4-NANO itself has not been tried.

## Install

Update Tessera Screen Manager and choose the Waveshare ESP32-P4-NANO + 10.1-DSI-TOUCH-A (marked Experimental) in
**New screen**. Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique
API/OTA keys.

The remote package is `packages/wavesharep4nano.yaml`; the checkout entry is `checkout/wavesharep4nano.yaml`. Both
combine `packages/core.yaml` with `packages/boards/wavesharep4nano.yaml`, which includes
`packages/hardware/esp32p4-c6.yaml` (the chip, its memory, the ESP32-C6 for Wi-Fi and the touch bus) and
`packages/hardware/waveshare-dsi-touch-a.yaml` (the panel's own I2C controller: its enable and its backlight). The
board needs ESPHome 2026.9.0 or newer. Logs come over UART0.

## Layout and capabilities

- Landscape: 1280 x 800 at 149 dpi, five columns of five cells, the standard look. Portrait: 800 x 1280, four columns
  of eight cells. The panel itself is 800 x 1280 and LVGL turns the picture and the touch, as on the other 10.1-inch
  P4 boards.
- 256 tiles over 16 pages, what the memory budget of a board with PSRAM allows ([TILE_MEMORY.md](TILE_MEMORY.md)).
- The backlight takes levels, so brightness, standby, night mode, Sleep, Wake and the alert's flashes all work. The
  level is a byte written over I2C, not a PWM pin (see below).
- Camera tiles, full-screen snapshots, live tile pictures, camera alerts and media artwork use the shared PSRAM
  implementation. Bluetooth for plugins comes with the ESP32-C6.
- GT911 reports pixel coordinates, with no resistive calibration. The controller's interrupt and reset lines are not
  wired on this carrier, so it is polled.
- No audio. The carrier has an ES8311 codec wired, but no ES7210 microphone ADC, and its audio has not been tried, so
  the board ships without the speaker and microphone packages rather than with untested ones.

## The panel's I2C controller at 0x45

The panel carries a small controller at I2C address 0x45, on the same bus as the touch chip, and both the panel's
enable and its brightness live in it:

| Register | What it does |
|---|---|
| 0x95 | the panel's enable, written 0x11 then 0x17 |
| 0x96 | the backlight's level, a byte from 0 to 255 |

**The enable has to happen before the display sets up.** ESPHome's `mipi_dsi` knows nothing about it: it only ever
writes 0x96 and never writes 0x95 at all. Waveshare do the enable inside `esp_lcd_new_panel_jd9365()`, before any DSI
traffic and unconditionally for every panel their driver supports
(Waveshare-ESP32-components, `display/lcd/esp_lcd_jd9365/esp_lcd_jd9365.c`):

```
0x45: 0x95 <- 0x11 ; 0x95 <- 0x17 ; 0x96 <- 0x00 ; wait 100 ms ; 0x96 <- 0xFF ; wait 1000 ms
```

Without it the panel never drives its side of the DSI link, so the host cannot complete a transfer: the generic
command FIFO buffers about 19 short writes and then never drains, `tx_param` spins in
`mipi_dsi_host_ll_gen_is_cmd_fifo_full`, and roughly 30 seconds later the task watchdog aborts the boot, ten times
over, into safe mode with a dark panel. Reported to ESPHome as
[esphome/esphome#21451](https://github.com/esphome/esphome/issues/21451).

`components/panel_i2c_enable` does the sequence at `setup_priority::IO`, after the I2C bus and before any display. An
`on_boot` in the board file cannot: the shared one in `packages/core.yaml` runs at priority -100, long after the
display has given up. With the enable in place the init sequence completes (202 commands, against 19 before) and
display setup takes about 2.7 seconds.

The backlight is the same controller. The carrier routes no PWM pin, so the output that
[`packages/features/backlight.yaml`](../packages/features/backlight.yaml) dims is a template output that writes
register 0x96, the register the vendor BSP writes in `bsp_display_brightness_set()`. The panel wiki quotes register
0x86; 0x96 is what works on this panel.

## Hardware references

- [Waveshare ESP32-P4-NANO wiki](https://www.waveshare.com/wiki/ESP32-P4-NANO) and the
  [10.1-DSI-TOUCH-A wiki](https://www.waveshare.com/wiki/10.1-DSI-TOUCH-A).
- Waveshare's board support package (Waveshare-ESP32-components): the JD9365 driver and the 0x45 enable.
- [ESPHome MIPI DSI](https://esphome.io/components/display/mipi_dsi/), model `WAVESHARE-P4-NANO-10.1`: the JD9365 init
  sequence and the timings for two lanes. There is no reset pin to give it here; the panel self-resets on power-up.
- I2C: SDA GPIO7, SCL GPIO8 (the touch bus of `hardware/esp32p4-c6.yaml`), shared by the GT911 and the 0x45
  controller.
- The ESP32-P4NRW32 module on this carrier has 16 MB flash and 32 MB of in-package PSRAM. Some batches ship a 32 MB
  flash module; such a board states `flash_size: 32MB` in its board file.

## What to report while testing

1. Successful boot, appearance in Tessera, and the log's first lines: the bus scan finding the touch chip and the
   controller at 0x45, the panel enable, and no watchdog or safe mode.
2. Correct colours and a stable picture across several page changes and cold starts.
3. Physical taps near each corner, slider drags and edge swipes, lying down and standing up.
4. The brightness setting across its range, standby after the timeout and the wake by touch, several times in a row,
   and night mode.
5. A full page of tiles, opening and closing the settings and detail cards.
6. The chip revision from the boot log, and whether the board is a NANO, a Module-DEV-KIT or a WIFI6-DEV-KIT carrier.
7. Free internal heap with a full layout, any reset or I2C errors, and how long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
