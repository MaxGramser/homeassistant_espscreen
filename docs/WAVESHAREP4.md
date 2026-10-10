# Waveshare ESP32-P4-86-Panel-ETH-2RO

The `wavesharep4` board file supports the relay-equipped 4-inch, 720 × 720 Waveshare 86 panel
(SKU 31570), with the shared screen UI in two columns and three rows. Display, capacitive
touch, dimmable backlight and Wi-Fi are configured. The board is experimental.

Waveshare documents this panel alongside the ESP32-P4-WIFI6-Touch-LCD-4B (SKU 31416), which has
the same main board in a different assembly and enclosure. The board file was first tried on the
relay-equipped model, and a community member has run it on a 4B as well. It is a different
board from the ESP32-S3-Touch-LCD-4B (`waveshare4b`).
See the manufacturer's [hardware comparison](https://docs.waveshare.com/ESP32-P4-WIFI6-Touch-LCD-4B#hardware-version-comparison).

## Hardware

| Part | Configuration |
| --- | --- |
| Processor | ESP32-P4, pre-v3 silicon, 360 MHz (`packages/hardware/esp32p4-c6.yaml`, shared with the Guition P4 panels) |
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

This board needs ESPHome 2026.9.0 or newer. It sets `engineering_sample: true` for
pre-v3 P4 silicon, including the revision 1.3 panel used during development. Firmware built
that way does not start on revision 3 silicon, and the other way round. Check the chip
revision in the serial installation output; a panel that reports v3.0 or higher needs
`engineering_sample: false` under `esp32:` in the screen's Override YAML.

## Installation

1. Install a release of ESP Screen Manager that lists this board and open **New screen**.
2. Select **Waveshare ESP32-P4-86-Panel-ETH-2RO** and enter the screen's name and Wi-Fi details.
3. Connect the panel's **USB TO UART** port with a data cable and select that port for installation.
   The native USB OTG port is a different connection. The installer generates the API and OTA keys;
   keep this screen's YAML for future updates.
4. ESP Screen Manager adds the screen to Home Assistant's ESPHome integration and allows its
   actions by itself ([Easy Setup](EASY_SETUP.md), chapter 3). A screen built elsewhere is added by
   hand: Home Assistant must reach the panel's ESPHome API, and the integration's device options need
   **Allow the device to perform Home Assistant actions** for tile taps to work.
5. Add the screen's tiles in ESP Screen Manager.

See [Easy Setup](EASY_SETUP.md) for the complete flow. Before the board is available in a published
release, developers can use `checkout/wavesharep4.yaml` with the
[checkout instructions](../checkout/README.md). Credentials belong in ignored
`checkout/secrets.yaml`, never in the board file.

The screen's generated YAML includes ESPHome's fallback hotspot and captive portal. If it cannot
join Wi-Fi, use the hotspot from a phone or computer to enter network details in a browser. Its
password is in the screen's own YAML. The panel has no touchscreen Wi-Fi credentials form.

The ESP32-C6 is a separate coprocessor. Flashing the P4 does not replace its firmware. If serial
logs show an SDIO or ESP-Hosted handshake failure, check the C6 firmware before changing Wi-Fi
credentials. See ESPHome's [coprocessor update documentation](https://esphome.io/components/update/esp32_hosted/).

## Scope and follow-up work

This board file uses **Wi-Fi only**. The board has Ethernet hardware, but this version does not
configure Ethernet. Ethernet support is planned as a separate contribution.

Relays, RS485 and microSD are not configured by this board file. The model name describes the
hardware fitted to the board; it does not mean these peripherals are enabled in firmware.

## Audio

The speaker (an ES8311 and an amplifier on GPIO53) and the microphones (an ES7210) are the screen's
audio through `features/audio.yaml`: a media player in Home Assistant, a Volume and a Microphone
setting under Extras, and the speaker and microphone that plugins such as the voice assistant use.
Both codecs share one I2S bus, which ESPHome lets them take in turns, so the board sets
`AUDIO_HALF_DUPLEX`:

- the bus runs at 16 kHz for both;
- the speaker lets go of the bus half a second after a sound, and the amplifier follows the sound,
  on while it plays and off just before the bus stops, so the DAC's clock is not heard;
- the microphone lets go of the bus whenever the speaker wants it, for any sound (an
  announcement, an answer, music, a plugin's tick), and listens again after; a wake word does not
  hear during that time (`features/audio-half-duplex.yaml`).

This replaces the `p4_audio` plugin, which brought the codecs to this board before. The audio has
been built for this board but not yet heard on one.

For Docker Desktop builds, keep compiler and build caches in container-local storage rather than
a macOS shared folder. The first build still has to obtain its dependencies; see
[Docker installation](DOCKER.md). Tile and layout edits do not require a firmware build.

## Hardware acceptance

Build and host-render checks do not replace testing on the physical panel. Before treating a
revision as supported, check cold start, Wi-Fi and API connection, colour order, touch at the
corners and during a drag, backlight dimming and waking, page navigation and OTA updates.
The board stays experimental until those checks are recorded for that hardware revision.
