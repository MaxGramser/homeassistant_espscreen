# Waveshare ESP32-P4-86-Panel-ETH-2RO

The `wavesharep4` board file supports the relay-equipped 4-inch, 720 × 720 Waveshare 86 panel
(SKU 31570), with the shared screen UI in two columns and three rows. Display, capacitive
touch, dimmable backlight, Wi-Fi, audio and the two relay outputs are configured. The board is experimental.

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
| Backlight | Boost enable GPIO33, inverted PWM on GPIO26 at 200 Hz |
| Touch | GT911, SDA GPIO7, SCL GPIO8, reset GPIO23, polled every 20 ms |
| Wi-Fi | ESP32-C6 over SDIO: reset GPIO54, clock GPIO18, command GPIO19, data GPIO14-17 |
| Relays | GPIO32 (Relay 1), GPIO46 (Relay 2), active-high; both off at every boot |
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

RS485 and microSD remain unconfigured. **Ethernet is not included in this change**;
Ethernet configuration and testing will be a separate contribution. Wi-Fi is used for these tests.

## Relays

The 86 Panel Bottom Board exposes two ordinary Home Assistant switch entities, **Relay 1** and
**Relay 2**. They are not configuration entities and do not appear under Extras: add them to tiles
or automations as needed. Both use `ALWAYS_OFF`, so a reboot does not restore an energised relay.
This is a boot policy, not a connection-loss watchdog. The state is the commanded GPIO state,
not physical contact feedback.

GPIO32 and GPIO46 are active-high, as in Waveshare's [bottom-board schematic](https://files.waveshare.com/wiki/ESP32-P4-WIFI6-Touch-LCD-4B/86_Panel_Bottom_Board.pdf)
and [relay implementation](https://github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-4B/blob/5a7a9a2823d77983c15b44a72934a7699e5d2d8b/firmware/brookesia/components/bsp_extra/src/bsp_board_peripherals.c).
The bare 4B assembly has no relay bottom board; these outputs concern the 86-Panel-ETH-2RO.

## Audio

The speaker (ES8311, amplifier GPIO53) and microphones (ES7210) keep the shared audio
interfaces `ts_speaker`, `ts_microphone` and `ts_media_player`. Existing plugins use these same
interfaces; no voice assistant or AI provider is added by this board support.

This branch selects `P4_AUDIO_TRANSPORT: "aec"` on the Waveshare P4. The shared I2S/TDM bus
can capture and play simultaneously. **Extras** in the editor and on the panel offers Volume,
Microphone, Microphone gain (0–36 dB in 3 dB steps, initially 30 dB), Automatic gain and
Echo cancellation. These are the board's ESPHome entities in HA, not separate editor settings.
The fixed playback-reference gain is unaffected by microphone gain and Automatic gain.

Echo cancellation can be turned on/off live. Off passes the selected microphone through while
keeping the adaptive filter current; it does not mute the microphone or switch to half-duplex.
The setting survives reboot. `Echo cancellation status` reports Enabled, Bypass, Starting or Error.

The codecs and the amplifier live in `packages/hardware/wavesharep4-audio/codecs.yaml`. Waveshare wires the
audio of the [ESP32-P4-WIFI6-Touch-LCD-7B](WAVESHAREP47B.md), the [ESP32-P4-WIFI6-Touch-LCD-7](WAVESHAREP47.md)
and the [ESP32-P4-WIFI6-Touch-LCD-10.1](WAVESHARE101.md) the same way, so those boards take the same codecs,
transports and settings. The Tab5 brings its own wiring for the same transport. Other boards do not select the
extended ES7210 driver, audio stack or AEC dependency.

For the original half-duplex path without the AEC library, override and rebuild:

```yaml
substitutions:
  P4_AUDIO_TRANSPORT: "i2s"
```

Gain and Automatic gain remain available. Echo cancellation is absent in that firmware and
its editor row is unavailable. A live switch does not change firmware size. See
[P4_AUDIO.md](P4_AUDIO.md) for processing, provenance, licenses and hardware validation.

For Docker Desktop builds, keep compiler and build caches in container-local storage rather than
a macOS shared folder. The first build still has to obtain its dependencies; see
[Docker installation](DOCKER.md). Tile and layout edits do not require a firmware build.

## Hardware acceptance

Build and host-render checks do not replace testing on the physical panel. Before treating a
revision as supported, check cold start, Wi-Fi and API connection, colour order, touch at the
corners and during a drag, backlight dimming and waking, page navigation and OTA updates.
The board stays experimental until those checks are recorded for that hardware revision.
