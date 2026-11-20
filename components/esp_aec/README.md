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
- Provide a live output bypass for AEC on/off. The DSP keeps adapting while bypassed;
  re-enabling changes the output selection on the next frame without replacing the handle.
  This saves neither DSP CPU nor firmware space. Incomplete DSP frames emit silence.
- `nlp_level` (normal, aggressive, very_aggressive): ESP-SR's level for how hard the residual is pressed down, set with
  `aec_set_nlp_level` on every handle the library makes. Left out, the library's own stays (aggressive in 2.5.5).
- `on_demand` with `set_needed(bool)`: at rest the DSP is not called and the microphone is handed on as it is, so a
  canceller that only a call needs costs nothing between calls. `at_work()` says whether it runs now.
- Reset the startup guard when the DSP handle is replaced. The diagnostic counter
  `startup_silence_frames()` counts skipped initial frames.

`tests/test_aec_startup.py` executes the actual process body with an instrumented
DSP boundary. It covers initial zeros, one-LSB input, reference-only input,
channel stride, later silence, bypass/resume, other modes and invalid/locked handles. Hardware
validation is still required after dependency, codec or enclosure changes.

See [P4_AUDIO.md](../../docs/P4_AUDIO.md) for configuration and dependency notices.
