# ESPHome 2026.11: the boards with echo cancelling do not build

## The symptom

A P4 board with echo cancelling (the Guition P4 panels, the reTerminal D1001, the Tab5) built with ESPHome 2026.11.0, as
ESPHome Device Builder now does, stops in the audio stack:
`'class esphome::esp_audio_stack::ESPAudioStackSpeaker' has no member named 'audio_dac_'; did you mean 'audio_dacs_'?`

## What we know

2026-11-18: ESPHome 2026.11 lets a speaker have several DACs and renamed `speaker::Speaker::audio_dac_` to `audio_dacs_`.
The pinned stack (245fc1ad, docs/P4_AUDIO.md) still uses the old name. Of the stack's own versions only the development
tag `v2026.12.0-dev` (651c3070) reads both, behind `ESPHOME_VERSION_CODE`, and it requires ESPHome 2026.10, which the
app's ESPHome (2026.9.0) and `min_version` (2026.6.2) are not.

The rest of the firmware builds with ESPHome 2026.11 and its LVGL 9.6 since 2026-11-18 (a 4-inch Guition built with
2026.6.2, 2026.9.0 and 2026.11.0, and ran on glass with 2026.11.0).

## Candidates

- Ask the stack for a commit that reads both names and keeps ESPHome 2026.6 to 2026.9, as 245fc1ad did for 2026.10.
- Move `min_version` and the app's ESPHome to 2026.10, then pin the stack's development tag (a release of its own,
  docs/RELEASING.md "ESPHome versions").

## The deciding experiment

A build of the Guition 10.1 (jc8012p4a1v3) with ESPHome 2026.6.2, 2026.9.0 and 2026.11.0 on the chosen pin.

## Pointers

`packages/hardware/parts/echo-cancel.yaml` (the pin), docs/P4_AUDIO.md "Sources and attribution".

## Solved: the stack in a fork, one commit on top (2026-11-19)

The pin moves to this project's fork of the stack (MaxGramser/esphome-audio-stack, branch `tessera-esphome-2026.11`,
6ffa32df): 245fc1ad and one commit that, from ESPHome 2026.11 on (`ESPHOME_VERSION_CODE`), hands the speaker's volume and
mute to `speaker::Speaker`, which drives every DAC there; with an older ESPHome the code is as before. The Guition 10.1
(jc8012p4a1v3, echo cancelling) built with it on ESPHome 2026.9.0 and 2026.11.0. Not yet flashed and heard on 2026.11.
The stack's own development version (v2026.12.0-dev) does the same but requires ESPHome 2026.10: once the app's
ESPHome and `min_version` reach 2026.10 the pin goes back to the stack. This file goes with the next release.
