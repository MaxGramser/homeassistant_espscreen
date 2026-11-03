# Opus encoding costs 11.8 ms a packet on the Guition 10.1

## The symptom
Screen camera's sound report: on the Guition 10.1 with four live tiles and voice_assist, 11.8 ms to encode one 20 ms
Opus packet (59 % of the packet's time on one core); on the reTerminal D1001 7.8 ms, and with one tile 5.1 to 6.8 ms
on both (2026-10-29). At complexity 0 already.

## What we know
The encoder runs in the screen_video server task; the cost rises with the screen's other load (tiles, JPEG decoding,
LVGL), so part of it is waiting for the core, not computing. Earlier (morning of 2026-10-29) a steady 36 to 46 % of
a core was measured for Opus alone on the D1001.

## Next step
Measure the encoder alone on an idle screen (cycle count around esp_opus_enc_process); check whether the build uses
the P4's FPU and SIMD paths of esp_audio_codec, and whether 16 kHz mono at 20 ms is the cheapest frame; consider
40 ms frames under pressure (half the calls) if latency allows. Compare with the voice assistant's own Opus use.

## Pointers
tessera-plugins plugins/screen_camera/components/screen_video/opus_sound.cpp, the "Sound:" report line in
screen_video.cpp.
