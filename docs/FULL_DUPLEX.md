# Experimental full-duplex panel audio

This is an opt-in experiment for the Waveshare ESP32-P4-86-Panel-ETH-2RO
(`wavesharep4`, also sold as ESP32-P4-WIFI6-Touch-LCD-4B). Hardware support alone
does not establish echo cancellation quality. Validate it with the actual speaker,
enclosure, microphone gain and playback volume before enabling it permanently.

## Configuration and rollback

Keep the physical voice pairing from [DEVICE_VOICE.md](DEVICE_VOICE.md), and add
the transport selection to the panel's Override YAML:

```yaml
substitutions:
  AUDIO_MODE: "voice"
  AUDIO_TRANSPORT: "aec"
```

Build from this experimental branch. The default is `AUDIO_TRANSPORT: "i2s"`,
which retains the original ESPHome transport. Setting it back to `i2s` and
rebuilding restores that transport. `AUDIO_MODE: "off"` excludes the audio
packages, including their external components and libraries. Other board
profiles do not include these packages.

With Audio Stack, optional tap feedback can play while the microphone is waiting
for a wake word. It remains suppressed during conversations, diagnostics and
other speaker playback. The default I2S path retains exclusive microphone/speaker
ownership for this feedback.

The first conversation integration negotiates duplex only for OpenAI direct
audio with replies on the panel itself. Claude and replies on an external speaker
retain half duplex. The local AEC reference cannot cancel arbitrary Sonos music
or a reply played by another device. A new panel with an older add-on also
retains half-duplex conversation behavior when the add-on does not accept duplex.

No provider API keys enter the firmware. The panel still uses the existing
authenticated add-on transport and bounded voice session. Wake recognition
stays local between conversations; duplex does not enable idle cloud capture.

## Research and implementation choice

Sources reviewed on 2026-10-05:

| Layer | Espressif provides | Integration chosen here |
| --- | --- | --- |
| Audio bus | [ESP-IDF I2S RX/TX](https://docs.espressif.com/projects/esp-idf/en/stable/esp32p4/api-reference/peripherals/i2s.html) on shared clocks | Hane `esp_audio_stack` owns both directions and exposes ordinary ESPHome microphone/speaker endpoints. |
| Echo cancellation | [ESP-SR AEC](https://docs.espressif.com/projects/esp-sr/en/latest/esp32p4/acoustic_echo_cancellation/README.html), including full-duplex modes | Hane `esp_aec` calls ESP-SR, with `fd_low_cost` and filter length 4. |
| Broader processing | [ESP-SR AFE](https://docs.espressif.com/projects/esp-sr/en/latest/esp32p4/audio_front_end/README.html) and [GMF AI Audio](https://github.com/espressif/esp-gmf/tree/main/elements/gmf_ai_audio) | Deferred. AEC alone avoids adding another AGC, wake detector or full GMF pipeline. |
| Codec control | [esp_codec_dev](https://github.com/espressif/esp-adf/tree/master/components/esp_codec_dev) supports ES7210 and ES8311 | Retain the existing ESPHome ADC/DAC configuration and ES7210 ALC extension. Do not configure a second codec owner in Audio Stack. |
| Conversation | [Espressif OpenAI WebRTC demo](https://github.com/espressif/esp-webrtc-solution/tree/main/solutions/openai_demo) demonstrates AEC and Realtime audio | Retain Tessera's add-on/provider boundary and device transport. The standalone demo is a reference, not a drop-in firmware for this panel. |

Direct integration of ESP-IDF and ESP-SR remains possible. It would require
maintaining the shared-bus lifecycle, DMA/buffer handling, playback reference
and ESPHome endpoint adapters ourselves. Hane already implements that layer;
its AEC algorithm is Espressif's, not an independently competing algorithm.
Successful full-duplex acoustic behavior has not yet been established on this
panel. Smooth standalone playback does not establish echo cancellation quality.

### Official guidance for the hardware-reference candidate

Espressif's [microphone design guidelines](https://docs.espressif.com/projects/esp-sr/en/latest/esp32p4/audio_front_end/Espressif_Microphone_Design_Guidelines.html)
recommend taking the echo reference after the DAC and before the power amplifier.
The reference and microphone must not clip at the intended playback volume.
Changing the AEC mode cannot compensate for a distorted reference, an incorrect
channel assignment or an unsuitable acoustic enclosure.

The [ESP-IDF 5.5.5 ES7210 example](https://github.com/espressif/esp-idf/blob/v5.5.5/examples/peripherals/i2s/i2s_codec/i2s_es7210_tdm/main/i2s_es7210_record_example.c)
uses Philips TDM with four 16-bit slots and MCLK at 256 times the sample rate.
That example records at 48 kHz; the candidate retains 16 kHz for the selected
AEC processing. It retains this board's pins, not the example board's pins.
The matching [I2S documentation](https://docs.espressif.com/projects/esp-idf/en/v5.5.5/esp32p4/api-reference/peripherals/i2s.html)
describes the shared-clock full-duplex bus. A second I2S controller is not needed
to capture microphones and the electrical reference together.

The [ES7210 datasheet](https://files.waveshare.com/wiki/common/ES7210-datasheet.pdf)
orders the TDM-I2S channels as MIC1, MIC3, MIC2 and MIC4. On this board MIC3 is
the electrical playback reference, so the candidate selects slot 0 for the
microphone and slot 1 for the reference. Physical ADC channel numbers and TDM
slot numbers are different. Verify the actual signal levels after flashing;
successful configuration generation cannot prove a physical signal mapping.

### Comparison with Waveshare's maintained voice firmware

The official [4B repository](https://github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-4B/tree/5a7a9a2823d77983c15b44a72934a7699e5d2d8b)
contains a maintained Brookesia/Xiaozhi voice application. Its
[firmware documentation](https://github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-4B/blob/5a7a9a2823d77983c15b44a72934a7699e5d2d8b/docs/firmware.md)
explicitly distinguishes that source from an image programmed at the factory.
Treat it as a source reference, not proof of the behavior of an individual
factory-installed panel. The basic audio-codec example is playback or microphone
loopback, without AEC.

At that source revision:

| Setting | Waveshare voice application | This experiment |
| --- | --- | --- |
| ES7210 channel order | MIC1, MIC3 reference, MIC2, MIC4 | Same slot mapping |
| Analogue input gain | 24 dB on connected physical channels MIC1, MIC2 and MIC3 | Existing microphone setting; fixed 24 dB reference gain |
| Bus | Standard stereo TX and four-slot TDM RX at 24 kHz | Four-slot TDM TX/RX at 16 kHz |
| Processor input | Both microphones plus reference, resampled together to 16 kHz | One microphone plus reference at native 16 kHz |
| DSP | ESP-SR AFE, FD low-cost, AEC and VAD enabled; AFE AGC and noise suppression disabled | Standalone ESP-SR AEC, FD low-cost |
| During a reply | Voice upload disabled; local wake-word interruption when the app is visible | Continuous processed input for conversational interruption |

The gain comes from `CODEC_DEFAULT_ADC_VOLUME` and the physical connected-channel
mask in [bsp_board_extra.h](https://github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-4B/blob/5a7a9a2823d77983c15b44a72934a7699e5d2d8b/firmware/brookesia/components/bsp_extra/include/bsp_board_extra.h),
applied by `bsp_extra_codec_set_voice_fs()` in
[bsp_board_extra.c](https://github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-4B/blob/5a7a9a2823d77983c15b44a72934a7699e5d2d8b/firmware/brookesia/components/bsp_extra/src/bsp_board_extra.c).
The [Xiaozhi application](https://github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-4B/blob/5a7a9a2823d77983c15b44a72934a7699e5d2d8b/firmware/brookesia/components/XiaozhiApp/XiaozhiApp.cpp)
selects that mask and routes slots 0, 2 and 1 to the processor as `MMR`.
Its [processor configuration](https://github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-4B/blob/5a7a9a2823d77983c15b44a72934a7699e5d2d8b/firmware/brookesia/components/XiaozhiApp/XiaozhiAudioProcessor.cpp)
enables AEC explicitly. The application depends on ESP-SR 2.4.7 and
esp_codec_dev 1.5.11, whereas this experiment uses its separately pinned stack.

The board's reference network includes approximately 24 dB resistive attenuation
before MIC3. A 24 dB reference-gain candidate is therefore supported by both the
circuit and Waveshare's source settings, but still requires actual level and
clipping checks. Do not simultaneously change gain, channel mapping, sample rate
and DSP pipeline: first compare the same stimulus with only reference gain
changed. Waveshare's wake-word interruption also does not establish that its
software supports arbitrary conversational interruption during playback.

## Dependencies to revisit on updates

- [ESPHome Audio Stack](https://github.com/n-IA-hane/esphome-audio-stack), release
  2026.10.2, pinned at `0482d741a938378ef948e3b8f3dd31536f9f2cc9`.
  Only `esp_audio_stack` and `esp_aec` are imported.
- At this pin, standalone AEC requests `espressif/esp-sr ^2.5.3` and
  `espressif/esp-dsp ^1.8.0`. These are version ranges. Record the resolved
  `dependencies.lock` with local build results when comparing updates.
- The stack selects `esp_audio_effects ~1.3` for pre-v3 P4 silicon. Do not
  override that with libraries built for revision 3 instructions. The board
  profile's `engineering_sample: true` describes the older supported revision.
- The optional `codec:` backend in that release requests
  `esp_codec_dev 2.0.0-beta5`. This experiment does not enable that backend.
- The separate `esp_afe` component uses Hane's GMF fork at
  `95c97b55b349894b95b34dcd357f8c81fd5be098` for output delivery and P4 task
  placement. This experiment does not import `esp_afe`. Re-evaluate that fork
  and its upstream status before adding dual-microphone enhancement or AFE.
- Keep upstream license notices with distributed firmware. ESPHome Audio Stack
  and its Espressif dependencies have their own licenses; some Espressif DSP
  libraries include hardware-specific redistribution terms and binary code.

## Licensing and redistribution

The selected Hane components are MIT licensed. Use, modification and
redistribution require retaining the copyright and permission notice. The
exact notice from the pinned checkout is preserved in
[hane-MIT.txt](licenses/full-duplex/hane-MIT.txt). The repository also contains
components with other licenses; importing these two components does not mean
every file in that repository is MIT licensed.

The resolved ESP-SR and esp_audio_effects licenses permit use with Espressif
products and require their notices to be retained. They impose hardware-use
restrictions beyond standard MIT. Their texts and ESP-DSP's Apache-2.0 text are
in [licenses/full-duplex/](licenses/full-duplex/). The P4 experiment runs on
Espressif hardware. These files cover the primary new audio dependencies,
not an exhaustive license bundle for the entire firmware and toolchain.

Public redistribution of a combined firmware binary needs a separate
compatibility review: Tessera is AGPLv3 and ESPHome runtime code is GPLv3,
whereas these Espressif audio libraries have hardware restrictions and some
binary-only implementations. Do not assume that retaining notices or fetching
an external component resolves those obligations. No additional linking
permission has been established in this research. This does not prevent the
local experiment; it remains an outstanding item before publishing binaries.
See the [ESPHome license](https://github.com/esphome/esphome/blob/dev/LICENSE),
Tessera's [LICENSE](../LICENSE) and [GNU guidance on incompatible libraries](https://www.gnu.org/licenses/gpl-faq.en.html#GPLIncompatibleLibs).

## Audio routing and levels

The existing board schematic pin assignment remains: MCLK 13, BCLK 12, LRCLK 10,
microphone DIN 11, speaker DOUT 9, amplifier enable 53. ES7210 and ES8311 remain
on their existing I2C addresses. See [WAVESHAREP4.md](WAVESHAREP4.md).

Capture uses the first microphone slot from 16-bit stereo I2S. The stack supplies
mono 16-bit 16 kHz PCM to the existing wake detector and voice consumer. This
experiment does not add dual-microphone beamforming. Playback uses mono 16 kHz.
The ES8311 stays at unity gain with the existing software volume control.

AEC uses the stack's software reference from post-volume speaker PCM. The
80 ms reference ring is buffer capacity, not a measured acoustic delay. The
100 ms speaker buffer bounds queued playback. DMA completion callbacks count
played frames for conversation truncation; accepted bytes alone would include
audio the user never heard.

The experimental profile uses two DMA descriptors. FD_LOW_COST processes 32 ms
frames; the stack aligns its DMA blocks to that frame size on this configuration.
The default six descriptors can therefore queue 192 ms of output, independently
of the software reference FIFO capacity. Two descriptors reduce that queue to
64 ms. This timing choice still requires hardware validation for cancellation
quality and scheduling headroom; it is not a measured acoustic-delay correction.

The board schematic also shows an analogue playback reference from ES8311
OUTP/OUTN to ES7210 MIC3P/MIC3N. This profile does **not** capture that channel:
ordinary stereo on SDOUT1 carries microphones 1 and 2. Using the hardware
reference requires a verified ES7210 TDM configuration, physical-slot mapping,
separate reference gain and compatible ES8311 output clocks. The current native
ES7210 schema at the published driver pin does not expose TDM. Do not enable a
second codec owner alongside it or treat the second ordinary microphone as the
reference.

A local hardware-reference candidate extends that existing ES7210 driver with
optional TDM and a separately configured reference ADC. It preserves microphone
gain and ALC controls, while keeping the reference at its own fixed analogue
gain and unity digital gain, excluded from ALC. The current reference gain is
24 dB; input levels, clipping and cancellation still require validation.
Hane's existing TDM input
path supplies the microphone and reference to the existing AEC implementation;
no replacement DSP algorithm is added.

This candidate uses four 16-bit Philips TDM slots and the stack's normal six DMA
descriptors. Both input signals now come from the same ADC stream, rather than
from a software playback FIFO. Existing upstream slot-level sensors expose the
microphone, reference and second microphone for validation. Confirm that the
ES8311 still plays correctly with these clocks as part of the hardware test.

The candidate currently depends on an unpublished local driver checkout. It is
not enabled by the configuration example above and is not a reproducible public
installation recipe yet. Hardware acceptance and a reviewed, immutable driver
dependency are required before incorporating it into the board's AEC package.

Keep the existing microphone analogue gain and ALC settings initially. If echo
suppression is poor, compare ALC on/off at fixed microphone and speaker levels
before adding more processing. Clipping or a badly aligned reference cannot be
fixed by simply increasing gain or choosing a more aggressive AEC mode.

For diagnostics, use the **Audio diagnostics** button supplied by the AEC
profile. It invokes the upstream stack's bounded diagnostic snapshot. The
add-on logs reply duration, speech-start phase and interrupted playback duration
without logging spoken content or provider credentials. A speech-start event
during speaker-only playback indicates residual echo or other audible input,
not by itself a network or buffering failure. Keep detailed stack telemetry
disabled in normal profiles; enable it temporarily in a private test override
when measuring underruns and processor timing.

## Conversation interruption

The version-2 prepare message advertises `duplex: true`. The add-on accepts it
in `listen` only for a supported local-reply session. During accepted duplex
sessions, capture continues through thinking and playback. Realtime semantic
VAD remains enabled and detects the new speech.

Playback messages and acknowledgements carry a monotonically increasing
`playback` number. On interruption the add-on cancels and joins the old sender,
sends `interrupt`, and waits for the panel to stop the speaker and acknowledge
`interrupted` with `played_ms`. The panel clears pending PCM before this barrier.
Late acknowledgements from an old playback cannot complete a new one.

The add-on then sends `conversation.item.truncate` for the unheard part of the
OpenAI audio response, following the [Realtime interruption contract](https://developers.openai.com/api/docs/guides/realtime-conversations).
The new microphone input is retained rather than cleared. Semantic VAD handles
generation cancellation. Stop, mute, silence and session deadlines still apply.

Reply generation currently retains the existing bounded whole-reply preparation.
Full duplex does not by itself change time to first reply into streamed playback.

## Resource and hardware acceptance

Espressif reports standalone FD_LOW_COST at 16 kHz/mono using 18.9 KB internal
RAM, 102.1 KB PSRAM and 11.5% CPU on a 400 MHz P4 with its documented cache
settings. Those are library benchmarks, not measurements of Tessera, this
360 MHz board profile or the complete integration. Measure firmware flash,
internal heap/DMA availability, PSRAM and audio underruns on the actual build.

Before accepting an update:

1. Validate both ordinary and AEC configurations. Confirm disabled profiles do
   not resolve or link the extra audio stack. Build only the affected P4 candidate.
2. Verify normal tiles, touch, Wi-Fi, volume, mute and wake behavior still work.
3. Check microphone capture and playback concurrently at several speaker volumes.
   In a quiet room, the reply alone must not trigger repeated new questions.
4. Speak over an answer. Check prompt stopping, retention of the beginning of
   the new question, no stale reply tail, and appropriate conversation context.
5. Repeat wake/conversation/stop cycles, including mute, timeout and disconnection.
   Return to local wake detection without indefinite cloud capture.
6. Check the standard transport, older panel protocol, Claude and external-output
   fallbacks separately. A browser emulator cannot establish physical AEC quality.

Keep local measurements and build logs outside the repository. Successful
compilation and simulated protocol tests do not replace these physical checks.
