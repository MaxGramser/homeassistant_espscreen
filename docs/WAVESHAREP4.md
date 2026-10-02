# Waveshare ESP32-P4-86-Panel-ETH-2RO

The `wavesharep4` profile supports the relay-equipped 4-inch, 720 × 720 Waveshare 86 panel
(SKU 31570), using the shared Tessera UI with two columns and three rows. Display, capacitive
touch, dimmable backlight and Wi-Fi are configured. The profile is experimental.

Waveshare documents this panel alongside the ESP32-P4-WIFI6-Touch-LCD-4B (SKU 31416),
which has a different main-board assembly and enclosure. This profile has been tried on the
relay-equipped model. It is also distinct from the ESP32-S3-Touch-LCD-4B (`waveshare4b`).
See the manufacturer's [hardware comparison](https://docs.waveshare.com/ESP32-P4-WIFI6-Touch-LCD-4B#hardware-version-comparison).

## Hardware

| Part | Configuration |
| --- | --- |
| Processor | ESP32-P4, pre-v3 silicon, 360 MHz |
| Memory | 32 MB flash, 32 MB hex PSRAM at 200 MHz |
| Display | ST7703, ESPHome `mipi_dsi` model `WAVESHARE-P4-86-PANEL`, reset GPIO27 |
| Display supply | Internal LDO channel 3 at 2.5 V |
| Backlight | Boost enable GPIO33, inverted PWM on GPIO26 at 100 Hz |
| Touch | GT911, SDA GPIO7, SCL GPIO8, reset GPIO23, polled every 20 ms |
| Wi-Fi | ESP32-C6 over SDIO: reset GPIO54, clock GPIO18, command GPIO19, data GPIO14-17 |
| USB logging | UART0 through the USB-to-UART bridge |

The assignments follow the [main-board schematic, page 1](https://files.waveshare.com/wiki/ESP32-P4-WIFI6-Touch-LCD-4B/ESP32-P4-WIFI6-Touch-LCD-4B.pdf).
The touch interrupt ends at a test point, so the controller is polled. The P4-side SDIO
signals in that schematic are the ones used here; the website's quick-reference table differs.
ESPHome supplies the display initialization and timings through its
[built-in panel model](https://esphome.io/components/display/mipi_dsi/).

Backlight output is limited to 80% of the PWM range, as in the
[community configuration linked by Waveshare](https://github.com/alaltitov/Waveshare-ESP32-P4-86-Panel-ETH-2RO/blob/2026.1.4/src/main.yaml).
The screen's brightness setting still covers 0-100% of that configured range.

This profile needs ESPHome 2026.9.0 or newer. It sets `engineering_sample: true` for
pre-v3 P4 silicon, including the revision 1.3 panel used during development. Revision 3
chips need a different build. Check the chip revision in the serial installation output;
do not use this binary on revision 3 hardware.

## Installation

1. Install a Tessera Screen Manager release containing this profile and open **New screen**.
2. Select **Waveshare ESP32-P4-86-Panel-ETH-2RO** and enter the screen's name and Wi-Fi details.
3. Connect the panel's **USB TO UART** port with a data cable and select that port for installation.
   The native USB OTG port is a different connection. The installer generates the API and OTA keys;
   keep this screen's profile for future updates.
4. Add the device through Home Assistant's ESPHome integration. If network discovery cannot reach it,
   enter its IP address in the integration's manual setup. Home Assistant must be able to reach the
   panel's ESPHome API, including when Home Assistant runs in Docker.
5. In the ESPHome integration's device options, enable **Allow the device to perform Home Assistant
   actions** to let tile taps control entities. Then add the screen's tiles in Tessera.

See [Easy Setup](EASY_SETUP.md) for the complete flow. Before the board is available in a published
release, developers can use `checkout/wavesharep4.yaml` with the
[checkout instructions](../checkout/README.md). Credentials belong in ignored
`checkout/secrets.yaml`, never in the board profile.

The generated device profile includes ESPHome's fallback hotspot and captive portal. If it cannot
join Wi-Fi, use the hotspot from a phone or computer to enter network details in a browser. Its
password is in the private device profile. The panel has no touchscreen Wi-Fi credentials form.

The ESP32-C6 is a separate coprocessor. Flashing the P4 does not replace its firmware. If serial
logs show an SDIO or ESP-Hosted handshake failure, check the C6 firmware before changing Wi-Fi
credentials. See ESPHome's [coprocessor update documentation](https://esphome.io/components/update/esp32_hosted/).

## Scope and follow-up work

This profile uses **Wi-Fi only**. The board has Ethernet hardware, but this version does not
configure Ethernet. Ethernet support is planned as a separate contribution.

Relays, RS485, microSD and audio are not configured by this base profile. The model name describes
the hardware fitted to the board; it does not mean these peripherals are enabled in firmware.

For Docker Desktop builds, keep compiler and build caches in container-local storage rather than
a macOS shared folder. The first build still has to obtain its dependencies; see
[Docker installation](DOCKER.md). Tile and layout edits do not require a firmware build.

## Hardware acceptance

Build and host-render checks do not replace testing on the physical panel. Before treating a
revision as supported, check cold start, Wi-Fi and API connection, colour order, touch at the
corners and during a drag, backlight dimming and waking, page navigation and OTA updates.
Keep the profile experimental until those checks are recorded for that hardware revision.
