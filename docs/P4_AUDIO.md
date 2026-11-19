# Waveshare P4 audio, gain and echo cancellation

This is hardware support for the **ESP32-P4-86-Panel-ETH-2RO**. No assistant, wake-word model,
AI provider, conversation backend, Spotify control or Ethernet implementation is included.
The two relays are ordinary HA switches; [WAVESHAREP4.md](WAVESHAREP4.md) describes them.

Three other Waveshare ESP32-P4 boards wire their audio exactly as the 86 panel does, per Waveshare's
schematics, and take the same codecs (declared in `packages/hardware/wavesharep4-audio.yaml`, the parts in `packages/hardware/parts/`), transports and
settings: the [ESP32-P4-WIFI6-Touch-LCD-7B](WAVESHAREP47B.md), the [ESP32-P4-WIFI6-Touch-LCD-7](WAVESHAREP47.md)
and the [ESP32-P4-WIFI6-Touch-LCD-10.1](WAVESHARE101.md). All three are experimental; their pages say who tried what.

## Which P4 boards have audio

| Board | Codecs | Transport | Echo cancellation | Extras |
| --- | --- | --- | --- | --- |
| Waveshare 86 panel, LCD-7B, LCD-7, LCD-10.1 | ES8311 + ES7210 | AEC by default, half-duplex I2S optional | Yes (ES7210 MIC3 reference) | Volume, Microphone, Microphone gain, Automatic gain, Echo cancellation |
| M5Stack Tab5 | ES8388 + ES7210 | AEC by default, half-duplex I2S optional | Yes | Volume, Microphone, Echo cancellation |
| Guition JC8012P4A1 (all builds), JC1060P470 (both), JC4880P443 | ES8311 alone | AEC by default on the codec's one bus; two I2S ports on it without the AEC libraries by choice | Yes: the codec's own feedback is the reference (below) | Volume, Microphone, Echo cancellation |
| CrowPanel Advanced 10.1 | NS4168 amplifier, PDM microphone | Two I2S buses | No | Volume, Microphone |
| reTerminal D1001 | ES8311 + ES7210 | Two I2S buses, the microphones' with AEC by default | Yes: the ES7210's MIC3 carries the ES8311's line output (below) | Volume, Microphone, Wake when moved, Echo cancellation |

The Guition panels' one ES8311 plays the speaker and reads an analogue microphone on its own input
(`packages/hardware/guition-p4-audio.yaml`, the part `parts/es8311-voice.yaml`). It has two transports, as the ES7210's
part has. The one with echo cancelling is the default ("The ES8311's own reference" below). The plain one, `AUDIO_TRANSPORT: "i2s"`
in a screen's Override YAML: the speaker and the microphone work at the same time without echo cancelling, two of
the chip's I2S ports share the codec's clock pins, the microphone's port giving the clocks (ESPHome's `primary`)
and the speaker's following them (`secondary`), as [@Eugen417](https://github.com/Eugen417) runs it on a
JC8012P4A1 V3 (#259). ESPHome runs a microphone only while something listens, so the board listens from the
start to keep the clocks running for the speaker. The Guition pages ([JC8012P4A1](JC8012P4A1.md),
[JC1060P470](JC1060P470.md), [JC4880P443](JC4880P443.md)) have the wiring and the sources.

### The ES8311's own reference

The ES8311 needs no wire for a playback reference: with its register 0x44 at 0x58 it sends two slots, the microphone
on the left and, on the right, the right slot of what it was given to play, sample for sample (Espressif's
`esp_codec_dev` sets the same). The default transport is built on it (`parts/es8311/aec.yaml`, `AUDIO_TRANSPORT: "aec"`): the pinned audio stack on the one bus, two slots each way, and the same echo cancelling as
the boards with an ES7210 (`parts/echo-cancel.yaml`). The reference is taken before the codec's volume.

Measured on a Guition JC8012P4A1 V3 with a firmware of nothing but this path (2026-11-17): noise under 4 kHz from the
board's own speaker, the level left in the microphone after the canceller, at rest and at work.

| Speaker volume | Canceller at rest | Canceller at work | Taken away |
| --- | --- | --- | --- |
| 15 % | -55.1 dBFS | -65.8 dBFS | 11 dB, down to the room's own noise |
| 20 % | -50.7 dBFS | -67.7 dBFS | 17 dB, down to the room's own noise |
| 25 % | -45.1 dBFS | -70.4 dBFS | 25 dB |
| 30 % | -38.6 dBFS | -75.8 dBFS | 37 dB |
| 75 % | -0.4 dBFS, clipped | -6.0 dBFS | 6 dB: the microphone was at its top |

So it works where the microphone does not clip, and at this microphone gain (24 dB before the canceller) it clips from
about half volume. Not measured: the volumes between 30 % and 75 %, a voice at the same time as the far end, and the
other Guition panels: the 7-inch and the 4.3-inch have the same codec and wiring and get the same transport on that ground, unmeasured.

### A microphone chip on a bus of its own

The reTerminal D1001 has the ES7210 on one I2S bus and the ES8311 on another, and Seeed's schematic puts the ES8311's
line output straight on the ES7210's MIC3. The default transport is built on it (`parts/es7210/split-aec.yaml`;
`AUDIO_TRANSPORT: "split"` in a screen's Override YAML leaves the canceller out): the microphones' bus in TDM through the pinned audio stack,
receive only, so the voice and the reference arrive in the same frames; the speaker keeps ESPHome's own I2S on its bus.
This reference is electrical and after the codec's volume, so it is as loud as the speaker is.

Measured on a reTerminal D1001 with a firmware of nothing but this path (2026-11-17), as on the Guition above:

| Speaker volume | Canceller at rest | Canceller at work | Taken away |
| --- | --- | --- | --- |
| 45 % | -39.2 dBFS | -62.6 dBFS | 23 dB |
| 65 % | -44.5 dBFS | -74.4 dBFS | 30 dB |
| 75 %, the media player's top | -31.4 dBFS | -87.9 dBFS | 56 dB |

The row at 55 % read 17 dB lower at rest than its neighbours and is left out: the series is not clean, so take the
direction from it, not each number. A level of -88 dBFS is close to digital silence, which says the canceller also
gates; what that does to a voice that speaks at the same time as the far end is not measured.

The same series on the Guition at the volumes of a call:

| Speaker volume | Microphone gain | Canceller at rest | Canceller at work | Taken away |
| --- | --- | --- | --- | --- |
| 60 % | 12 dB | -12.4 dBFS | -46.6 dBFS | 34 dB |
| 60 % | 24 dB | -2.9 dBFS, clipped | -16.3 dBFS | 13 dB |
| 75 % | 0 to 24 dB | -18.4 to -0.4 dBFS | 6 to 7 dB lower | 6 to 7 dB at every gain |

At the top volume the microphone does not clip with its gain down and the canceller still takes little away: the
distortion is the amplifier's or the loudspeaker's, and a canceller cannot work out a sound that is distorted on its
way. So on these panels the canceller needs a microphone gain of 12 dB or less, and at the top volume voice switching
is what keeps the echo away (docs/CALLS.md, "Echo"). Not measured: the volumes between 60 % and 75 %.

### A voice beside the board

What a canceller does to the voice of whoever stands at the board matters as much as the echo it takes away. Measured
on the Guition with the same firmware, a voice counting aloud beside it (a laptop's loudspeaker), microphone gain 12 dB,
speaker at half volume, the level at the canceller's output:

| | Canceller's level aggressive (the library's own) | normal |
| --- | --- | --- |
| The voice alone, canceller at rest | -47.5 dBFS | -44.5 dBFS |
| The voice alone, canceller at work | -46.1 dBFS | -43.2 dBFS |
| The voice while the board's speaker plays noise, canceller at work | -52.0 and -47.2 dBFS | -44.9 and -45.4 dBFS |
| The same with the canceller at rest (voice and echo together) | -25.2 dBFS | -29.1 dBFS |

So a silent far end costs the voice nothing at either level, and while the far end sounds the voice loses about 6 dB at
aggressive and about 2 dB at normal, with the echo still under the voice. The two runs were not at the same distance
from the laptop, so compare within a column. The transports of this section run at normal (`AUDIO_ECHO_LEVEL`).

Two things heard in a call between this Guition and a reTerminal D1001 in another room (2026-11-17): with the microphone
at 12 dB and nothing given back, the voice beside the Guition was too soft at the other end, so the 12 dB are given back
after the canceller (`AUDIO_VOICE_GAIN`); and with echo cancelling on and voice switching off the call sounded best.

### Only while it is needed

A canceller that runs whenever the microphone does costs a share of one core all day (Espressif gives 11.5 % for this
mode on a P4), and on these boards the microphone always runs, for the wake word and for the codec's clocks. On a
Guition 10.1 a page turn held the main loop 218 ms on average with the canceller always at work and 183 to 191 ms
without it in the firmware (20 turns each over the same five pages, 2026-11-17). So on the
two transports of this section the canceller works on demand (`AUDIO_ECHO_ON_DEMAND`, `esp_aec`'s `on_demand`): it
works for as long as the screen's voice goes out to a far end, a call or the doorbell's Talk (`talk_uplink` says so),
and at rest it hands the microphone on as it is without running the DSP. Its status reads Resting then. The boards with
an ES7210 on the speaker's bus keep it at work whenever the microphone runs, as a voice assistant that listens while the
screen plays has always had it there.

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
**Echo cancellation status** is Enabled, Resting (on a board whose canceller works on demand, between calls), Bypass, Starting or Error. Enabled means cancellation
is selected and the DSP initialized; it is not a measurement of echo suppression quality.

The ES7210's part takes `AUDIO_TRANSPORT: "aec"` by default, since its MIC3 carries a playback reference. To omit
the audio stack/AEC libraries entirely, select `AUDIO_TRANSPORT: "i2s"` in Override YAML and rebuild
(`P4_AUDIO_TRANSPORT` and `TAB5_AUDIO_TRANSPORT`, the old names, still work in firmware 0.58 and go in the release
after). This keeps
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

- Hane's [ESPHome Audio Stack](https://github.com/n-IA-hane/esphome-audio-stack/tree/245fc1ad34b443996479c645d20e2960d99bdc31)
  provides the full-duplex bus and standard ESPHome microphone/speaker adapters. Only
  `esp_audio_stack` is fetched, from this project's fork of it
  ([MaxGramser/esphome-audio-stack](https://github.com/MaxGramser/esphome-audio-stack/tree/6ffa32dfc2a271cf258ec974e4bef624b34ce05d),
  branch `tessera-esphome-2026.11`): 245fc1ad and one commit of ours. Our [AEC wrapper](../components/esp_aec/README.md)
  derives from the same repository and keeps its MIT notice.
  The pin is chosen by the ESPHome versions a screen builds with (docs/RELEASING.md, "ESPHome versions"): ESPHome
  2026.10 made the ring buffer's handle a function, the stack's 2026.10.2 release still read it as a field and no
  longer compiled there, and its releases from 2026.11.0 on require ESPHome 2026.10. The pinned commit is the
  stack's own step in between, which reads the handle either way, so it builds with the app's ESPHome, with
  `min_version` and with the newest. Moving the pin past it waits for a `min_version` of 2026.10.
  ESPHome 2026.11 renamed the speaker's `audio_dac_` to `audio_dacs_` and drives the DACs in its own `set_volume` and
  `set_mute_state`. The stack's own versions that know this require ESPHome 2026.10, so the fork adds one commit on top
  of 245fc1ad: from ESPHome 2026.11 on (`ESPHOME_VERSION_CODE`) the speaker hands volume and mute to the base class, with
  an older ESPHome it is as before. One pin builds with ESPHome 2026.6 to 2026.11. The stack's own development version
  already does the same but requires ESPHome 2026.10: once the app's ESPHome and `min_version` reach 2026.10, the pin
  goes back to the stack itself and the fork is no longer needed.
- Espressif **ESP-SR 2.5.5** provides the AEC algorithm. ESP-DSP retains the reviewed `^1.8.0`
  constraint; the pinned stack supplies its audio-effects dependency, an exact version for each
  chip revision (`1.3.0~1` before revision 3, `1.4.3` from revision 3 on).
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
A contributor ran the same codecs, AEC transport and amplifier on a pre-v3 ESP32-P4-WIFI6-Touch-LCD-7
(speaker, microphones, playback with capture and echo cancellation worked). The LCD-7B (rev3 silicon) and
the LCD-10.1 have not run them yet. Of the Guition panels, a JC8012P4A1 V3 runs the same codec wiring in full
duplex with a build of its owner's own; the other Guition boards have not run their audio yet.

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

With the codecs shared by the four Waveshare boards, the AEC builds on ESPHome 2026.9.0 come to these
OTA images: the 86 panel 3,745,648 bytes, the LCD-7 3,709,136 and the LCD-7B 3,282,928. The two pre-v3
boards resolve esp_audio_effects 1.3.0~1 as above; the LCD-7B, built for rev3 silicon, resolves
esp_audio_effects 1.4.3 with the same ESP-SR 2.5.5 and ESP-DSP 1.8.2.
