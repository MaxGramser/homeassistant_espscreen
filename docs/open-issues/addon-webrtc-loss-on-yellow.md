# The add-on loses WebRTC packets on a Home Assistant Yellow

## The symptom
With a camera full screen on a Guition 10.1 (the tablet's stream, 2 Mbit/s "Sharp" 1280x720), the add-on's frame
watch reported 625 to 2037 packets lost per 10 s, 80 to 140 frames missing, 200 to 1800 NACKs and up to 25 PLIs,
while the Guition's own stream (0.8 Mbit/s) lost 0 to 84. The sound of that stream came 0.4 s behind on average and
up to 6 s. With one live tile per screen and no full view the loss vanished (0 to 84), 2026-10-29 20:47 to 21:50.

## What we know
- The loss is between go2rtc (inside Home Assistant core) and the add-on's aiortc receiver, on the same machine: the
  RTSP from the screen is TCP and cannot lose, and the sender's own counters showed 0 packets left behind (Screen
  camera 0.6.15).
- Supervisor stats during the full view: add-on 29 to 48 % of the machine (a 4-core Yellow: more than one core),
  879 MB; HA core 4 to 6 %. The add-on's asyncio loop runs on one core; near a full core it does not drain aiortc's
  UDP socket in time and the kernel drops.
- The full view costs 11.4 JPEGs a second of 56 KB, 12.4 ms CPU each (about 14 % of a core alone), on top of
  receiving and decoding; with five tiles per screen the add-on held about eight WebRTC streams.
- go2rtc's own counters (its API on 11984 inside core) are not reachable from outside; the SSH add-on would be.

## Ruled out
Wi-Fi (both screens at -26 to -39 dBm), the sender (0 left behind after 0.6.15), the viewer (the screen's buffer
now rides out 1.2 s of jitter).

## Candidates
1. The JPEG encode of the full view and the H.264 decode run on the asyncio thread; moving them to an executor
   frees the loop to drain the socket.
2. aiortc's UDP receive buffer (SO_RCVBUF) is the default; a larger one rides out the loop's busy moments
   (net.core.rmem_max in the container may cap it).
3. Fewer pictures a second for a full view: a screen shows about 8 a second at most anyway.

## The deciding experiment
On the house or the bench with the same scenario: measure packets lost per 10 s with (1), then (2), then (3), one
at a time, with Supervisor stats beside it. The first that brings the loss to the Guition's 0 to 84 is the fix.

## Pointers
screen_manager/app/camera_source.py (rtc, webrtc, hear), live_stream.py (pictures, sounds), the frame watch's log
line "Live <camera>: N frames ... packets lost". The peer session's measurements of 2026-10-29 are in
.esphome/home/release-test-2026-10-29.txt on the owner's machine.
