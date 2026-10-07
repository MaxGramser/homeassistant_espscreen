# Optional P4 echo cancellation

Based on `esp_aec` from [ESPHome Audio Stack](https://github.com/n-IA-hane/esphome-audio-stack/tree/0482d741a938378ef948e3b8f3dd31536f9f2cc9/esphome/components/esp_aec).
The original MIT license is preserved in LICENSE. The audio bus still comes from
that pinned upstream project. The Espressif DSP implementation is neither copied
nor replaced here.

Local changes:

- Pin ESP-SR to the tested version, 2.5.5.
- Before the first nonzero microphone/reference frame in FD low-cost mode,
  return exact silence without submitting all-zero frames to the DSP. On the
  tested pre-v3 P4, a single initial zero frame otherwise left echo cancellation
  ineffective. Once either input is nonzero, every frame reaches the original
  DSP, including later silence and echo tails. No amplitude threshold, synthetic
  noise, extra gain or periodic reset is added.
- Reset the startup guard when the DSP handle is replaced. The diagnostic counter
  `startup_silence_frames()` counts skipped initial frames.

`tests/test_aec_startup.py` executes the actual process body with an instrumented
DSP boundary. It covers initial zeros, one-LSB input, reference-only input,
channel stride, later silence, other modes and invalid/locked handles. Hardware
validation is still required after dependency, codec or enclosure changes.

See [P4_AUDIO.md](../../docs/P4_AUDIO.md) for configuration and dependency notices.
