# Waveshare P4 audio, gain and echo cancellation

This is hardware support for the **ESP32-P4-86-Panel-ETH-2RO**. No assistant, wake-word model,
AI provider, conversation backend, Spotify control or Ethernet implementation is included.
The two relays are ordinary HA switches; [WAVESHAREP4.md](WAVESHAREP4.md) describes them.

## Interfaces and settings

The board keeps `ts_microphone`, `ts_speaker` and `ts_media_player`. Its new transport replaces
only the physical microphone/speaker endpoints. The shared mixer, resamplers, announcement and
media inputs, media-player volume mapping and microphone mute still serve existing consumers.
All speaker audio uses the same electrical reference, including plugin sounds and announcements.

Under **Screen settings → Extras**, in Tessera and on the panel:

- **Microphone gain**: analogue gain, 0–36 dB in 3 dB steps; initially 30 dB.
- **Automatic gain**: ES7210 codec ALC (automatic level control), initially on. This is separate
  from ESPHome voice-assistant gain or noise suppression. It does not adjust the reference ADC.
- **Echo cancellation**: initially on, changes live and is restored over reboot. When off,
  the selected microphone is passed through. The adaptive filter continues to receive input
  so turning cancellation on again does not resume a filter frozen before a volume/room change.
  This bypass does not save DSP CPU or flash, mute capture, or switch the bus to half-duplex.

These are ESPHome entities; HA, the editor and panel change the same settings. Gain/ALC failures
retain the last accepted value and try to restore the previous codec registers. The diagnostic
**Echo cancellation status** is Enabled, Bypass, Starting or Error. Enabled means cancellation
is selected and the DSP initialized; it is not a measurement of echo suppression quality.

The P4 board selects `P4_AUDIO_TRANSPORT: "aec"` in this branch. To omit the audio stack/AEC
libraries entirely, select `P4_AUDIO_TRANSPORT: "i2s"` in Override YAML and rebuild. This keeps
the original half-duplex I2S transport, gain and ALC. No AEC entity is present in that build.
Other boards retain their default codecs and transport; the Tab5 can opt into the same
AEC transport with its own wiring ([Tab5 notes](TAB5.md#optional-echo-cancellation)). The extended codec is named
`es7210_extended` so importing it for this P4 cannot silently replace another board's driver.

## Processing and reference

The codecs share one physical I2S bus: MCLK13, BCLK12, LRCLK10, DIN11 and DOUT9.
The ES7210 emits four 16-bit Philips TDM slots at 48 kHz, ordered MIC1, MIC3, MIC2, MIC4.
Slot 0 supplies the microphone, and slot 1 supplies ADC3, the electrical playback reference.
ADC3 remains at 24 dB analogue gain, unity digital gain and no ALC. There is one bus owner
and no separate software-loopback delay estimate. The stack converts the selected microphone
and reference together from 48 kHz to 16 kHz before AEC, keeping their relative timing aligned.
The microphone endpoint supplies mono 16 kHz PCM. The speaker, mixer and player keep 48 kHz
playback; AEC bypass changes neither rate. Native I2S retains its original 16 kHz bus.

This uses the pinned audio stack's existing Espressif sample-rate converter, without another
AEC implementation. Conversion increases runtime buffer and processing requirements; verify
continuous capture/playback and cancellation on hardware after changing the bus rate.

Espressif FD low-cost AEC uses filter length 4. The reviewed startup fix skips only completely
zero initial frames before the first real mic/reference input. Later silence and echo tails
always reach the DSP. Bypass keeps the same frame size and stream format, with an atomic
selection once per frame; it does not destroy or replace the DSP handle while audio runs.
Missing inputs/handles, lock failures and incomplete DSP output produce silence and an error
return, not stale output. No custom echo-cancellation algorithm has been added.

## Sources and attribution

- Hane's [ESPHome Audio Stack](https://github.com/n-IA-hane/esphome-audio-stack/tree/0482d741a938378ef948e3b8f3dd31536f9f2cc9)
  provides the full-duplex bus and standard ESPHome microphone/speaker adapters. Only
  `esp_audio_stack` is fetched from that pinned version. Our [AEC wrapper](../components/esp_aec/README.md)
  derives from the same repository and keeps its MIT notice.
- Espressif **ESP-SR 2.5.5** provides the AEC algorithm. ESP-DSP retains the reviewed `^1.8.0`
  constraint; the pinned stack supplies its audio-effects dependency for pre-v3 silicon.
  Dependency resolution must be recorded and revalidated when versions change.
- The [ES7210 extension](../components/es7210_extended/README.md) builds on ESPHome's driver and
  the earlier gain/ALC work, with TDM and independently configured reference gain.
  Its original MIT/Python and GPLv3/runtime notices remain.
- Hardware behavior follows the [ES7210 datasheet](https://files.waveshare.com/wiki/common/ES7210-datasheet.pdf),
  [Espressif TDM example](https://github.com/espressif/esp-idf/blob/v5.5.5/examples/peripherals/i2s/i2s_codec/i2s_es7210_tdm/main/i2s_es7210_record_example.c)
  and [Waveshare codec setup](https://github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-4B/blob/5a7a9a2823d77983c15b44a72934a7699e5d2d8b/firmware/brookesia/components/bsp_extra/src/bsp_board_extra.c).

Espressif dependency notices are kept under [licenses/p4-audio](licenses/p4-audio/). They are
not relicensed under Tessera's AGPL. Review combined binary redistribution terms before
publishing firmware; retaining notices alone does not establish compatibility.

## Validation and remaining hardware tests

The earlier audio work was exercised on one pre-v3 Waveshare P4 (revision 1.3). Those results
are not acceptance of this port. Tab5, D1001 and other hardware are not validated by this change.

Focused tests exercise real driver register writes, reference isolation, failed-write recovery,
initial zero frames and AEC bypass/resume. Compile the affected configuration, then check on the panel:

1. Cold boot, existing tiles, touch, brightness, Wi-Fi and HA connection.
2. Both relay entities and commanded states; off again after reboot. Contact behavior requires
   a separate physical check; publishing a switch state does not prove contact movement.
3. Volume and microphone mute, gain/ALC changes through HA/editor/panel, and settings after reboot.
4. Clean speaker onset/end, microphone capture and no playback stutter with capture running.
5. Compare microphone/reference/processed levels with cancellation enabled and bypassed at
   the same volume and distance, including user speech during playback.
6. Repeated AEC toggles, cold starts and normal background sounds, without stale buffers or a
   false success after a driver failure.

Voice-plugin behavior and Assist integration are later tests, not features of this hardware branch.
Ethernet is deferred to a separate change when its cabling and hardware test are available.

### Local build check (ESPHome 2026.9.0)

| P4 transport | OTA image (bytes) | Reported static RAM (bytes) | AEC/audio stack present |
| --- | ---: | ---: | --- |
| AEC | 3,646,208 | 143,584 | Yes |
| Native I2S | 3,538,816 | 139,652 | No |

The AEC build resolved ESP-SR 2.5.5, ESP-DSP 1.8.2 and esp_audio_effects 1.3.0~1.
Both variants compile with the corrected board boot hook. Generated source retains the shared
screen initialization and gain controls; native I2S excludes the AEC and audio-stack components.
Neither build contains a voice assistant, wake-word component or Ethernet configuration.
Static RAM does not include runtime buffer/DSP allocations; measure those on hardware.
These are build results from the earlier 16 kHz bus configuration, not size measurements
or acoustic acceptance of the 48 kHz playback path.
