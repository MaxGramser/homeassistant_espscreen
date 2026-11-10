# Calls between screens

A call is a screen's camera and microphone to another
screen's glass and speaker, both ways, through the add-on. The doorbell's Talk is the first user of the same voice path
(docs/DOORBELL.md).

## The voice

A screen's microphone goes up as plain 16 kHz, 16-bit mono PCM in 20 ms parts: a chunked POST to `/camera/<token>/talk` on
the camera port the screen already uses (`talk_uplink.h`, the add-on's `talk_bridge.py`). No codec on the screen, 256 kbit/s,
every P4 with a microphone. The add-on's answer comes once the far end stands, so a key says it is live only then.

## What a live picture costs today, measured

Before anything is changed for calls, a reTerminal D1001's camera shown full screen on a Guition 10.1 through Home Assistant
(RTSP to go2rtc, WebRTC to the add-on, H.264 decoded, a JPEG for the glass, 2026-11-10):

| What | Measured |
|---|---|
| Glass to glass, a flip of light in front of the camera until it shows on the other glass, filmed at 30 fps | about 230 ms (19 flips; the delay of the filming itself taken off with a reflection of the same flip in the glass) |
| Pictures a second | 13.5 to 15 of the camera's 15 |
| On the receiving screen, a picture | 5.1 ms to decode, 17 ms to lay out, no picture passed, the panel never ran dry |
| The add-on, everything (WebRTC, H.264 decode of 1280x720, JPEG, sending) | 13 % of one core of an Apple M1 Max at 15 pictures a second |

A Raspberry Pi 4 core is several times slower than an M1 core, so the same work is estimated at half to three quarters of
a Pi 4 core per direction of a call. Not measured on a Pi. That is what the quality steps of a call are for: every second
frame and a smaller JPEG when the add-on falls behind.

## Media

A call's picture is read straight from the other screen's own video server (RTSP over TCP, `screen_source.py`, video only),
decoded by the add-on and sent to the glass as a JPEG for its size, as any live camera's. A D1001 to a Guition 10.1, both
directions at once (2026-11-10): about 290 ms glass to glass with 13 pictures a second, against 230 ms for one direction
through Home Assistant, the same within what the filming can tell. The voice, marked `X-Sound: talk`.

What a clean voice took, measured on the real route with a clean tone in place of the voice and the Mac's microphone at the
far speaker (a D1001 to a Guition 10.1, 2026-11-10):

| | Sound thrown away, in 38 s | Longest hole | Purity at its worst | Parts waiting on the way, on average |
|---|---|---|---|---|
| Run-up 80 ms, cut back above 600 ms, 13 pictures a second at the glass's size | 5.2 s | 1.9 s | -23 dB | 159 to 241 ms |
| Run-up 200 ms, cut back above 1 s, no new run-up at a moment's emptiness, at most 10 pictures a second and 960 pixels a side | none | 80 ms | +8 dB | 6 to 11 ms |

The network cuts a voice where it likes, also inside a sample (6 of 1334 pieces in one call). One odd byte handed on turns
everything after it into noise, so `talk_bridge.Voice` passes on whole parts of 20 ms only.

## Signalling

The add-on holds every call (`calls.py`, pure and tested without Home Assistant): one call a screen, busy, a ring nobody answers
is missed after 45 s, both ends gone, a doorbell's ring goes first (the call is held and comes back). A screen says what a finger
did with the event `esphome.screen_call` (`action`: list, dial, cancel, answer, decline, end, camera, mic; `to`, `video`, `key`).
The add-on answers with the op `call` (`s`: out, ring, live, held, end) and the list with the op `contacts`, in parts of twelve
rows so a house of thirty screens fits. Home Assistant gets one event per call: `esp_screens_call_started`, `_answered`,
`_missed` and `_ended` (from, to, video, seconds).

## The Call tile

`screen.call`, on a board with the module `call`. In its inspector: **Calls**, the list of screens or one screen that a tap calls at
once, and **Kind of call**, video where both ends can or sound only.

## Echo

While one side speaks the other side's microphone goes down by 18 dB, for a quarter of a second after the last word (`calls.VoiceSwitch`).
A screen that cancels echo itself (`echo_cancel` in its capabilities) is left alone. The doorbell's Talk is always switched.

## The ring

The screen rings on its own speaker, at full volume whatever its volume is set to, and goes back to its volume when the ring
ends. 1.4 and 1.9 kHz: what these small speakers carry best.

## The picture in a call

The other screen's picture lies beside the keys, as on a doorbell, and nothing of LVGL's lies over it. Over the whole glass with the
keys over it was tried and given up for now: docs/open-issues/call-picture-over-the-whole-glass.md.
