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
