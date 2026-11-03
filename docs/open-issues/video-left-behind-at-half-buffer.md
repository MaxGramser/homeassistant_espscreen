# A screen's video leaves a viewer behind once half its send buffer is on the way

## The symptom
Screen camera's video skips a viewer's pictures until the next key frame ("left behind for a full connection") far
more often than a full connection explains: on a reTerminal D1001 at 2.2 Mbit/s about 36 times a minute (2026-10-29,
21:00), and about 9 a minute after Screen camera 0.6.15 (21:42), at 1 to 2 Mbit/s over Wi-Fi. Each time the viewer's
picture stands still until a key frame comes.

## What we know
The video asks `select()` whether a viewer's socket is writable (rtsp_server.cpp, `writable_`). lwIP marks a TCP
socket not writable once its free send buffer is at or below TCP_SNDLOWAT, by default half of TCP_SND_BUF (opt.h,
`TCP_SNDLOWAT`; api_msg.c sets SENDMINUS after a write), or once the queue holds TCP_SNDQUEUELOWAT segments. With
TCP_SND_BUF at 65534 bytes that is about 32 KB unacknowledged: 0.2 s of video at 1.3 Mbit/s, which Wi-Fi through the
ESP32-C6 has on the way all the time. The sound had the same test and skipped 1 to 3 packets a second; Screen camera
0.6.15 sends sound with MSG_DONTWAIT and counts only EAGAIN as full (0 sound packets left behind since). The video kept
the select test, because a picture of 50 to 200 KB does need most of the buffer.

## Ruled out
A slow viewer: the app receives the stream through Home Assistant's go2rtc, which reads at once, and the counts fall
with fewer live tiles on the sending screen (less of its own load), not with the viewer.

## Candidates
- Send a picture with MSG_DONTWAIT and keep what did not fit per viewer, sent first next time (as 0.6.15 does for
  sound), so a viewer is left behind only when a whole picture's worth stays unsent.
- A lower TCP_SNDLOWAT for the screen's build, so `select()` says full near full.
- A larger send buffer for the video's sockets only.

## The deciding experiment
The same two screens showing each other's camera full screen: the left behind count a minute and the viewer's
"pictures waited" line with the current test, then with MSG_DONTWAIT and a pending buffer. The counts as Home
Assistant sensors (screen_video's behind_, left_out_, dropped_ and the sound's left behind) would let anyone read
them without Debug mode.

## Pointers
tessera-plugins plugins/screen_camera/components/screen_video/rtsp_server.cpp (`writable_`, `serve_`, `send_sound_`,
`left_behind`), screen_video.h (`left_behind`, the counters), the screen_video report lines (screen_video:104 and
:120). ESP-IDF components/lwip/lwip/src/include/lwip/opt.h and src/api/api_msg.c.
