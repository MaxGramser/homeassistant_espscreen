# Calls between screens

Work in progress: this document grows with the steps it describes. A call is a screen's camera and microphone to another
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
