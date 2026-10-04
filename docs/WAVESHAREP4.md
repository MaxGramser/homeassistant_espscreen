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

## Optional audio

Audio is **off by default**. To include it, open the screen's firmware profile in Tessera,
add one of these choices to **Override YAML**, then build and install that profile:

```yaml
substitutions:
  AUDIO_MODE: "test"
```

| Mode | Included |
| --- | --- |
| `off` | Display, touch and Wi-Fi. No codec drivers, audio entities or wake-word models. |
| `hardware` | ES7210 microphone ADC, ES8311 speaker DAC, I²S audio, saved audio settings and tap sound. |
| `test` | Hardware plus local speaker, microphone and wake-word tests. |
| `voice` | Hardware plus opt-in voice through the add-on, by touch or local wake-word detection. No diagnostic recording engine. |

Use `test` for hardware acceptance. Nothing records or listens for a wake word at startup.
Voice-assistant sessions and speech transport are separate work, and are not part of these tests.
The integration branch adds them in the separate [voice mode](DEVICE_VOICE.md).
Other board profiles do not include these packages.

The codecs share the touch I²C bus: ES7210 at `0x40`, ES8311 at `0x18`.
Audio uses MCLK GPIO13, BCLK GPIO12, LRCLK GPIO10, microphone input GPIO11, speaker output
GPIO9 and amplifier enable GPIO53. Connect a speaker suitable for the board to its speaker socket.
Capture and playback take turns on the same I²S bus; this does not provide full-duplex audio or
acoustic echo cancellation.

**Settings → Audio** on the panel, its configuration entities in Home Assistant, and
**Screen settings → Audio** in Tessera all change the same saved values. The editor shows audio
only when the device actually exposes those entities. Controls include microphone mute,
automatic gain, speaker volume and tap sound; test and voice modes also offer a wake-word choice. Voice mode adds a saved Wake word enabled switch, initially off.
The speaker's software volume controls the user percentage, with the ES8311 DAC fixed at unity gain.

- **Test speaker** plays a two-second tone at the selected volume.
- **Test microphone** records five seconds, shows a countdown in its row, then plays the recording
  through the connected speaker. The recording stays in PSRAM and is cleared after playback.
- **Test wake word** listens for at most 30 seconds. Choose Okay Nabu, Hey Jarvis, Alexa or
  Hey Mycroft first. Detection feedback appears in the test row. These are the standard ESPHome
  microWakeWord models; the test does not start a voice assistant.
- **Stop** is available during a test. Muting the microphone stops capture. A new test first
  stops the previous one; tap sounds never interrupt a test.

The board defaults to 30 dB analogue microphone gain, 0 dB fixed digital gain and automatic
level control (ALC) enabled with a +12 dB ceiling. These are starting values, not a measured
recognition-accuracy guarantee. Only the automatic-gain switch is exposed in the UI. For a
specific installation, the hardware package also accepts YAML substitutions:

```yaml
substitutions:
  AUDIO_MODE: "test"
  AUDIO_MICROPHONE_GAIN: "30dB"
  AUDIO_FIXED_DIGITAL_GAIN: "0dB"
  AUDIO_ALC_MAX_GAIN: "12dB"
```

ALC controls digital gain, independently of analogue microphone gain. Disabling it restores
`AUDIO_FIXED_DIGITAL_GAIN`. The ES7210 extension is kept outside the panel renderer, as a
[pinned external component](https://github.com/woozer/esphome/commit/ff380e19d41d0671975a44dd433091b035d45888);
the ES8311 and I²S components remain standard ESPHome drivers. ESPHome downloads this component
when an audio mode is selected; no local driver files or separate add-on are required.
