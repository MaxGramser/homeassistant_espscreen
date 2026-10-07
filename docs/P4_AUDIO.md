# Optional P4 audio and echo cancellation

The Waveshare ESP32-P4-86-Panel-ETH-2RO (`wavesharep4`) can include microphone,
speaker and acoustic echo cancellation without an AI provider. Audio is excluded
by default. Other board profiles do not select these components or libraries.

In the screen's **Override YAML**, choose:

```yaml
substitutions:
  AUDIO_MODE: "test"
  AUDIO_TRANSPORT: "aec"
```

Build and install this configuration. `test` includes the existing local speaker,
five-second microphone recording/playback and wake-word tests. Use `hardware`
instead to omit the test UI and wake-word models. `AUDIO_TRANSPORT: "i2s"` restores
the original half-duplex ESPHome audio transport. `AUDIO_MODE: "off"` excludes both
audio transports, even when `AUDIO_TRANSPORT` is set to `aec`.

This package supplies ordinary ESPHome microphone and speaker endpoints. It does
not start a conversation, upload audio, require API keys or include an OpenAI or
Claude client. Wake-word testing does not start a voice assistant. Simultaneous
audio processing alone does not implement conversational interruption; a consumer
must separately handle that interaction.

## Hardware and processing

- ES7210 captures four 16-bit Philips TDM slots at 16 kHz. The SDOUT1 order is
  MIC1, MIC3, MIC2, MIC4. Slot 0 is the microphone; slot 1 is the electrical
  playback reference from the ES8311 output. There is one codec owner.
- The reference ADC keeps 24 dB analogue gain and unity digital gain, without
  ALC. Microphone gain remains 30 dB by default, with its existing automatic-gain
  setting. Reference gain must not follow microphone gain or automatic gain.
- Hane's ESPHome Audio Stack owns the shared I2S bus and feeds microphone and
  reference into Espressif's FD low-cost AEC, with filter length 4. Its normal
  six DMA descriptors are retained. There is no software-reference delay guess.
- The microphone endpoint supplies mono 16-bit PCM at 16 kHz after AEC. The
  local recording test preserves every mono sample; its two peak indicators
  show the same processed channel. The I2S transport retains stereo input.
- ES8311 stays at unity gain. The speaker endpoint applies the user's software
  volume. Tap sounds may share the AEC bus with capture, but never interrupt
  another sound or an audio test.

Pin assignments and installation are in [WAVESHAREP4.md](WAVESHAREP4.md).
The implementation follows the [ES7210 datasheet](https://files.waveshare.com/wiki/common/ES7210-datasheet.pdf),
the [ESP-IDF TDM example](https://github.com/espressif/esp-idf/blob/v5.5.5/examples/peripherals/i2s/i2s_codec/i2s_es7210_tdm/main/i2s_es7210_record_example.c)
and the [Waveshare audio codec setup](https://github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-4B/blob/5a7a9a2823d77983c15b44a72934a7699e5d2d8b/firmware/brookesia/components/bsp_extra/src/bsp_board_extra.c).

## Dependencies and local fixes

The audio bus is fetched from [ESPHome Audio Stack](https://github.com/n-IA-hane/esphome-audio-stack)
at `0482d741a938378ef948e3b8f3dd31536f9f2cc9`. Only `esp_audio_stack` is imported
from that source. The small [AEC wrapper](../components/esp_aec/README.md) and
[ES7210 extension](../components/es7210/README.md) are included here with their
original licenses and documented changes. No private checkout or local override
is required. Generated P4 entries make these components available; ESPHome only
compiles them when the selected audio package uses them.

The AEC wrapper pins ESP-SR 2.5.5 and prevents completely zero initial frames from
disabling useful cancellation on the tested pre-v3 P4. After the first nonzero
frame, all input, including silence and echo tails, reaches the original DSP.
This is a narrow startup workaround, not another echo-cancellation algorithm.
ESP-DSP and the audio stack's pre-v3 audio-effects dependency retain upstream's
version constraints. Record resolved versions when validating an update.

Only the relay-equipped pre-v3 Waveshare P4 has been used for physical development.
Recorded-input comparison, playback and spoken interruption were exercised on
that setup. Local audio functions were also exercised with the extracted board-only
build; cold-start echo suppression still needs separate hardware validation.
Validate cold start, clean playback onset, recording duration, gain, tap sound,
wake tests and echo suppression at the actual speaker volume and distance.
Background sound, enclosures and other hardware require further testing. A local
speaker or microphone test by itself does not prove echo suppression.

## Licenses

Hane's imported code and AEC wrapper retain their MIT notices. ESPHome code keeps
its MIT/Python and GPLv3/runtime terms. The primary Espressif dependency licenses
are preserved in [licenses/p4-audio](licenses/p4-audio/). ESP-SR and audio effects
include hardware-specific restrictions and binary libraries; they are not
relicensed under Tessera's AGPL. Review the combined firmware's redistribution
terms before publishing binaries; keeping notices alone does not establish
license compatibility.
