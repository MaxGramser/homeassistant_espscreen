# Waveshare ESP32-P4-WIFI6-Touch-LCD-10.1

The `waveshare101` board file supports the 10.1-inch Waveshare ESP32-P4-WIFI6-Touch-LCD-10.1 (SKU 33672, and 33150
for the -EN version), an 800 × 1280 MIPI-DSI panel on Waveshare's ESP32-P4 main board. The shared screen UI runs lying
down at 1280 × 800 with a grid of five by five cells, the same glass and grid as the 10.1-inch Guition JC8012P4A1.
Display, capacitive touch, dimmable backlight, Wi-Fi and audio are configured. The board is experimental.

## Hardware

| Part | Configuration |
| --- | --- |
| Processor | ESP32-P4, pre-v3 silicon, 360 MHz (`packages/hardware/esp32p4-c6.yaml`, through `packages/hardware/waveshare-esp32p4.yaml`) |
| Memory | 32 MB flash, 32 MB hex PSRAM at 200 MHz |
| Display | JD9365, ESPHome `mipi_dsi` model `WAVESHARE-P4-NANO-10.1`, two lanes, reset GPIO27 |
| Display supply | Internal LDO channel 3 at 2.5 V |
| Backlight | PWM on GPIO26 at 1 kHz, not inverted |
| Touch | GT911 family, SDA GPIO7, SCL GPIO8, no reset or interrupt pin, polled every 20 ms |
| Wi-Fi | ESP32-C6 over SDIO: reset GPIO54, clock GPIO18, command GPIO19, data GPIO14-17 |
| Audio | ES8311 (0x18) and ES7210 (0x40) on the touch bus, I2S MCLK GPIO13, BCLK GPIO12, LRCLK GPIO10, DOUT GPIO9, DIN GPIO11, amplifier GPIO53 |
| USB logging | UART0 through the USB-to-UART bridge |

The main board is the one the ESP32-P4-86-Panel-ETH-2RO (`wavesharep4`) uses: the chip, the Wi-Fi co-processor, the
touch bus and the audio codecs are pin for pin the same, and both board files include
`packages/hardware/waveshare-esp32p4.yaml`. What differs is the glass, the touch panel's wiring and the backlight,
which is not inverted here and runs at 1 kHz.

The display, touch and backlight settings come from a community ESPHome configuration for this board that has run on a
wall for months. ESPHome supplies the panel's initialization and timings through its
[built-in panel model](https://esphome.io/components/display/mipi_dsi/), shared with Waveshare's 10.1-inch DSI panel
for the ESP32-P4-Nano. LVGL turns the picture and the touch together, so the touch panel reports the panel's own pixels
and needs no transform.

Lying down is LVGL's 270 degrees on this board. A screen hung the other way round takes another angle from the
Rotation setting, without a new build.

This board needs ESPHome 2026.9.0 or newer, the version the shared Waveshare audio is built with. It sets
`engineering_sample: true` for pre-v3 P4 silicon, which is what the board this file was written from carries. Firmware
built that way does not start on revision 3 silicon, and the other way round. Check the chip revision in the serial
installation output; a board that reports v3.0 or higher needs `engineering_sample: false` under `esp32:` in the
screen's Override YAML.

## Tried on the glass

Built from `checkout/waveshare101.yaml` with ESPHome 2026.9.0 and installed over USB on a board with
a pre-v3 ESP32-P4, then updated over Wi-Fi. Touch in all four corners and a drag, the colour order, the
backlight's levels, standby and waking on a touch, the rotation lying down and standing up, and page
switching work. Tiles were added through ESP Screen Manager, which takes the shape the screen reports
for a board it does not ship yet.

## Installation

1. Install a release of ESP Screen Manager that lists this board and open **New screen**.
2. Select **Waveshare ESP32-P4-WIFI6-Touch-LCD-10.1** and enter the screen's name and Wi-Fi details.
3. Connect the board's **UART** USB port with a data cable and select that port for installation. The installer
   generates the API and OTA keys; keep this screen's YAML for future updates.
4. ESP Screen Manager adds the screen to Home Assistant's ESPHome integration and allows its actions by itself
   ([Easy Setup](EASY_SETUP.md), chapter 3). A screen built elsewhere is added by hand: Home Assistant must reach the
   board's ESPHome API, and the integration's device options need **Allow the device to perform Home Assistant
   actions** for tile taps to work.
5. Add the screen's tiles in ESP Screen Manager.

See [Easy Setup](EASY_SETUP.md) for the complete flow. Before the board is available in a published release,
developers can use `checkout/waveshare101.yaml` with the [checkout instructions](../checkout/README.md). Credentials
belong in ignored `checkout/secrets.yaml`, never in the board file.
