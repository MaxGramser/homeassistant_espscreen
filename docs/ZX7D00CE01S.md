# Panlee ZX7D00CE01S-V13, experimental

The **Panlee ZX7D00CE01S-V13**: a 7-inch 800 x 480 panel over RGB, GT911 capacitive touch, an ESP32-S3 with 8 MB octal
PSRAM and 16 MB flash, and an I2S speaker output. The board file follows an ESPHome configuration a board owner ran on
the glass. A board owner ran this firmware on a ZX7D00CE01S-V13 (2026-10-29): it boots, joins Tessera, and its
colours, touch, brightness and standby work. Physical acceptance by the project has not been performed.

## Install

Update Tessera Screen Manager and choose **Panlee · 7 inch** (ZX7D00CE01S-V13, marked Experimental) in **New screen**.
Follow [Easy setup](EASY_SETUP.md) to create a profile with its own name, Wi-Fi references and unique API/OTA keys.
Choose the correct USB port, or download the firmware to flash with ESPHome Web from your own computer.
Tessera adds it to Home Assistant by itself once it is on your Wi-Fi; then add its tiles.

The remote package is `packages/zx7d00ce01s.yaml`; the checkout entry is `checkout/zx7d00ce01s.yaml`.
Both combine `packages/core.yaml` with `packages/boards/zx7d00ce01s.yaml`. The logs go out over UART0.

## Layout and capabilities

- Landscape: 800 x 480, four columns of four cells. Portrait: 480 x 800, two columns of seven cells.
- The standard look at 133 dpi, as the other 7-inch 800 x 480 boards, so a tile keeps its size in millimetres.
- The backlight takes levels: brightness is a percentage, and standby, night mode, Sleep, Wake and the alert's flashes
  are enabled.
- Camera tiles, full-screen snapshots, live tile pictures, camera alerts and media artwork use the shared PSRAM
  implementation. Their operation on this board still needs physical verification.
- GT911 reports pixel coordinates, polled, with no calibration (the owner's configuration needed none).
- LVGL uses a 12 % draw buffer, as the other 800 x 480 boards do.
- The speaker output (I2S, BCLK GPIO19, LRCLK GPIO20, DOUT GPIO4, an external DAC with no I2C codec) stays unused.

## Hardware references

- Display: ESPHome `mipi_rgb` with the `RPI` model (no init sequence). DE GPIO39, HSYNC GPIO5, VSYNC GPIO38, PCLK
  GPIO9, a 16 MHz inverted pixel clock (the defaults of `rpi_dpi_rgb`, which the owner's configuration used; `mipi_rgb`
  would default to 40 MHz). HSYNC pulse 10, back porch 40, front porch 40; VSYNC pulse 6, back porch 31, front porch 18.
- Colour lines as they ran: red GPIO10-14, green GPIO21, 0, 46, 3, 8, 18, blue GPIO17, 16, 15, 7, 6.
- I2C for the GT911: SDA GPIO48, SCL GPIO47, 400 kHz. The touch panel is polled; its reset and interrupt lines are not
  used.
- Backlight: GPIO45 (a strapping pin), a PWM at 1 kHz.

## What to report while testing

1. Successful boot and appearance in Tessera.
2. Correct colours (red and blue not swapped) and a stable picture across several page changes and cold starts. A
   picture that drifts sideways, flickers or has shifted colours points at the display block and its pixel clock.
3. Physical taps near each corner, slider drags and edge swipes, lying down and standing up. Touch that lands mirrored,
   swapped or short of the edges points at the touch transform or a missing calibration range.
4. The brightness setting across its range, standby after the timeout and the wake by touch, several times in a row,
   and night mode. Report any restart, a dark screen that does not wake, or lost touch after a wake.
5. A full page of tiles, opening and closing the settings and detail cards.
6. Camera tile pictures, full-screen camera images and camera alerts, including repeated opens and closes.
7. Free internal heap with a full layout (the Heap Free sensor under Diagnostic), any reset or I2C errors, and how
   long the screen stayed running.

Do not publish Wi-Fi passwords or API/OTA keys with logs.
