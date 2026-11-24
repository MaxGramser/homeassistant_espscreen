# Freenove FNK0104N, 3.5 inch, experimental

The **Freenove FNK0104N** is the 3.5-inch board of Freenove's ESP32-S3 display series: a 320 × 480 IPS panel with an
ST77922 TDDI controller over QSPI, built-in capacitive touch over I2C, and an ESP32-S3 with 16 MB flash and 8 MB octal
PSRAM. Tessera runs it lying down at 480 × 320, a quarter turn of the panel. The 2.8-inch and 4-inch boards of the same
series (`FNK0104A`, `FNK0104B` and `FNK0104S`) have different glass and controllers, and this board file is not for them.

Derived from Freenove's `Freenove_ESP32_S3_Display` repository (`ST77922.cpp`, `ST77922.h`, `ST77922_Touch.h`); it has
not yet been compiled or tested on real hardware, so the board is **experimental**.

## Install

Update Tessera Screen Manager and choose **Freenove · 3.5 inch, FNK0104N** (marked Experimental) in **New screen**. Follow
[Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique API/OTA keys, and flash it
over USB.

The remote package is `packages/freenovefnk0104n.yaml` and the checkout entry `checkout/freenovefnk0104n.yaml`. Both
combine `packages/core.yaml` with `packages/boards/freenove-fnk0104n.yaml` and `packages/hardware/freenove-fnk0104n.yaml`.

> [!NOTE]
> The ST77922 LCD reset is tied to the board's reset/power rail rather than a dedicated GPIO (`RST = -1`). If the
> screen stays blank immediately after a USB flash or software restart, unplug and replug power (a cold power cycle) so
> the panel initializes cleanly into QSPI mode.

## Layout and capabilities

- Lying down 480 × 320, two columns of two cells; standing up 320 × 480, one column of three. The standard look at
  165 dpi.
- The backlight is a PWM pin (GPIO41) at 20 kHz: brightness is a percentage, and standby, night mode, Sleep, Wake and the
  alert's flashes are enabled.
- The built-in ST77922 TDDI touch controller uses a 16-bit register map compatible with ESPHome's `st7123` driver (I2C
  address `0x55`) and reports pixel coordinates directly, so there is no touch calibration.
- The display uses `mipi_spi` (`model: CUSTOM`, `bus_mode: quad`) with `transform: disabled` (LVGL rotates the canvas
  instead of relying on `MADCTL.MV`) and `draw_rounding: 4` (ST77922 QSPI requires 4-pixel aligned window bounds).
- No camera package yet: camera tiles, snapshots and media artwork are not included. The board has the PSRAM for them,
  but nobody has tried them on it.

## Hardware references

| Part | Pins | Notes |
| --- | --- | --- |
| Display (ST77922, QSPI) | CLK GPIO12, D0–D3 GPIO11/13/14/9, CS GPIO10, 40 MHz | `color_order: rgb`, `invert_colors: true`, `draw_rounding: 4` |
| Touch (ST77922 TDDI, I2C) | SDA GPIO38, SCL GPIO39, INT GPIO47, RST GPIO48 | I2C address `0x55`, ESPHome `st7123` driver |
| Backlight | GPIO41 | PWM at 20 kHz |
| Standby key | GPIO0 | BOOT button |
| Battery ADC *(unconfigured)* | GPIO8 | 2:1 voltage divider |
| Audio ES8311 *(unconfigured)* | MCK 17, BCK 18, WS 21, DOUT 15, DIN 16, PA 1 | Shares I2C bus (GPIO38/39) |
| RGB LED *(unconfigured)* | GPIO40 | WS2812 |
| microSD *(unconfigured)* | CLK 5, CMD 4, D0–D3 GPIO6/7/2/3 | SDMMC 4-bit |

- [Freenove ESP32-S3 Display repository](https://github.com/Freenove/Freenove_ESP32_S3_Display).
- [ESPHome `mipi_spi`](https://esphome.io/components/display/mipi_spi/) and [`st7123` touchscreen](https://esphome.io/components/touchscreen/st7123/).

## What to report while testing

1. A successful boot and appearance in Tessera (note whether a cold power cycle was needed after flashing).
2. Correct colours (check `color_order: rgb` and `invert_colors: true`) and a stable picture lying down and standing up.
3. Taps near each corner, slider drags and edge swipes, both ways up (confirm touch orientation against LVGL rotation).
4. The brightness setting across its range, standby after the timeout and wake by touch, and night mode.
5. `sensor.<screen>_heap_free` with a full layout, any reset or Wi-Fi drop, and how long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
