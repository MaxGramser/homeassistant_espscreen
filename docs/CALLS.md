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

A call has video only between screens that both run the Screen camera plugin with its part Video: that plugin is the
screen's video server, and without it a call is sound only (the editor says so under the Call tile's Kind of call).
A call's picture is read straight from the other screen's own video server (RTSP over TCP, `screen_source.py`, video only),
decoded by the add-on and sent to the glass as a JPEG for its size, as any live camera's. A D1001 to a Guition 10.1, both
directions at once (2026-11-10): about 290 ms glass to glass with 13 pictures a second, against 230 ms for one direction
through Home Assistant, the same within what the filming can tell. The voice, marked `X-Sound: talk`.

What a clean voice took, measured on the real route with a clean tone in place of the voice and the Mac's microphone at the
far speaker (a D1001 to a Guition 10.1, 2026-11-10):

| | Sound thrown away, in 38 s | Longest hole | Purity at its worst | Parts waiting on the way, on average |
|---|---|---|---|---|
| Run-up 80 ms, cut back above 600 ms, 13 pictures a second at the glass's size | 5.2 s | 1.9 s | -23 dB | 159 to 241 ms |
| Run-up 200 ms, cut back above 1 s, no new run-up at a moment's emptiness, at most 10 pictures a second and 720 pixels a side | none | 80 ms | +8 dB | 6 to 11 ms |

The network cuts a voice where it likes, also inside a sample (6 of 1334 pieces in one call). One odd byte handed on turns
everything after it into noise, so `talk_bridge.Voice` passes on whole parts of 20 ms only.

## Ready before the answer

A screen's camera starts with its first viewer (Screen camera 0.7.0, docs/CAMERA.md "A camera nobody uses"), and the
add-on's reader of a screen's video takes a moment to find its first frame. Measured on a Guition 10.1 and a reTerminal
D1001 (2026-11-22), with the reader started at the answer: the first picture 1.7 to 3.0 seconds after the answer, and
4.7 to 5.3 seconds for a camera's first use since the screen started, when its encoder is made as well.

So a video call's cameras start while it rings (`Manager.call_prepare`, `live_stream.Live.keep`): from the first ring
the add-on reads both screens' video, exactly as it will in the call. Each camera, its encoder and the add-on's decoder
then stand when the call is answered, and the link a screen opens finds its source running. Nobody sees a picture
before the answer: a source without a link sends nothing to a glass. The camera's dot shows on both screens while the
call rings, because the cameras run. A call that ends unanswered lets the sources go, and each camera stops and gives
its memory back by itself. A call straight between two screens is not prepared: the add-on's sources have no part in it.

And a stream that waits for its first picture stays alive (`screen_source.ScreenSource.quiet`). A screen gives up on a
stream that is quiet for 6 s (`live_view::QUIET_MS`) and then says the camera has no picture; a call answered at once,
before its cameras stood, could wait about that long. While no picture comes and nobody speaks, the source sends
silence to whoever listens, as a call with sound alone does.

## Signalling

The add-on holds every call (`calls.py`, pure and tested without Home Assistant): one call a screen, busy, a ring nobody answers
is missed after 45 s, both ends gone, a doorbell's ring goes first (the call is held and comes back). A screen says what a finger
did with the event `esphome.screen_call` (`action`: list, dial, cancel, answer, decline, end, camera, mic; `to`, `video`, `key`).
The add-on answers with the op `call` (`s`: out, ring, live, held, end) and the list with the op `contacts`, in parts of twelve
rows so a house of thirty screens fits. Home Assistant gets one event per call: `esp_screens_call_started`, `_answered`,
`_missed` and `_ended` (from, to, video, seconds, and `key`, the same in every event of one call).

A screen always gets out of a call. ESP Screens answers the end or the decline of a call it does not hold (it started again in the
middle of one) with that call's end, and a screen whose hang-up gets no answer within two and a half seconds ends the call itself.

## Ringtone

What rings on a screen that is called is chosen on the editor's Events page, under **Calls**: a sound that comes with the
app or one cut from a file of your own, for every screen or one screen. A ring's op `call` carries its link (`rt`), and
the screen plays it back to back while it rings. docs/SOUNDS.md has the whole of it.

## The Call tile

`screen.call`, on a board with the module `call`. In its inspector: **Calls**, the list of screens or one screen that a tap calls at
once, and **Kind of call**, video where both ends can or sound only.

## Echo

Two things keep a voice from coming back out of the other loudspeaker, and both are a call's own choices, the same on both screens:

- **Voice switching.** While one side speaks the other side's microphone goes down by 18 dB, for a quarter of a second after the last
  word (`calls.VoiceSwitch`). Its price: the two cannot speak at once.
- **Echo cancelling**, on a board with a canceller (`echo_cancel` in its capabilities). A side whose canceller is at work is not
  switched.

Each has a small key in the call, in the top corner on the keys' side, smaller and quieter than the keys a call is run with: one
person speaking (`mdi:account-voice`) for voice switching, an ear (`mdi:ear-hearing`) for echo cancelling, which is there only when a
side of the call has a canceller. A press on either screen changes it for the call: the screen says `switch` or `echo` with
`esphome.screen_call` (`video` 1 for on), and ESP Screens tells both screens with the op `call` in the state `set` (`vs`, `ec`), as
the live message does when the call starts. A board with a canceller puts it to work or to rest as the call says and leaves it as
it found it when the call ends.

A call starts with echo cancelling on, and with voice switching only where it is needed: when one of its screens has no canceller.
Two screens that both cancel echo start without it, and either key brings it. The switch **Call voice switching** of each screen
(in Home Assistant, under its configuration; on as it comes) lets a screen say it never wants its calls to start with it. The
doorbell's Talk is always switched.

## Screen to screen

A call's media can go straight between the two screens, with ESP Screens only connecting them. Each screen serves its
own camera and voice to the other one and takes the other's the same way (`call_serve.h`): a small server on port 8555
answers `GET /call/<token>.mjpeg` with the stream a live view already plays, pictures as JPEG and the voice as `audio/L16`
parts every 20 ms, the heads of its parts as ESP Screens writes them. The pictures are the camera's frames the screen is
handed for its own view, scaled to at most 720 pixels a side and made into JPEG by the chip's own encoder
(`picture_engine::encode`), ten a second at most; the voice is the microphone's parts after the board's own processing.

- **Who may.** A screen says `call_direct` in its hello (a P4 with a microphone). A call goes direct only between two
  screens that both say it and both have their switch **Direct calls** on (`calls.DIRECT_SWITCH`). No firmware has that
  switch yet: the route has not run on a board, so until it has, every call goes through ESP Screens. The switch comes
  back (`packages/features/audio-player.yaml`, a template switch named Direct calls, off as it comes) with the proof.
- **The token.** ESP Screens makes one for each direction of each call. The live message brings a screen the token it
  serves under (`ds`) and, as `l`, the other screen's address with the other's token; there is no `tk`. A screen answers
  only under its token, only the other screen's address, and only while the call is live.
- **The fall back.** A screen whose stream the other one does not come for within four seconds says `direct` with
  `video` 0 in `esphome.screen_call`; ESP Screens then sends both the live message again with its own links, and that
  call goes through it from there. Two addresses that cannot reach each other (a guest network, client isolation, a
  VLAN) cannot be told from here, so the attempt decides.

Not run on a board yet (2026-11-17): it compiles for a Guition JC8012P4A1 V3 and a reTerminal D1001. Voice switching
on the screens themselves is not built, so a direct call relies on the boards' echo cancelling. What a look before it
found, for the measurements still to make:

- An ESP32-P4 does not decode H.264 in hardware: the block encodes only. Espressif's software decoder reaches 7 to 10
  pictures a second at 1280x720 with both cores to itself (its own figures), which a screen that also draws does not have.
- JPEG both ways is the route Espressif's own call between two P4 boards takes: the hardware codec encodes and decodes
  720p far faster than a call needs, one direction at a time behind one lock.
- The camera's frames are scaled by the PPA on the way, the device the picture engine already shares.
- Through the app a call between these two boards showed 7 to 8 pictures a second each way, and once 3 from the
  Guition while it also showed the other's picture: the number a direct call has to beat.

## Do not disturb

The switch **Do not disturb** of each screen (on the screen's settings page under Extras, in the app's Extras card and in Home
Assistant, as the ringtone and the voice switching's choice are: docs/SETTINGS.md; off as it comes, kept by the screen). On, a
call to the screen is refused at once: nothing rings or lights up there, the caller reads that the screen does not want to be
disturbed, and the list of screens shows it. ESP Screens reads the switch from Home Assistant (`calls.quiet`). The doorbell is not a
call and still rings. As a switch it takes an automation: on at night, off in the morning.

## The picture in a call

The other screen's picture lies beside the keys, as on a doorbell, and nothing of LVGL's lies over it. Over the whole glass with the
keys over it was tried and given up for now: docs/open-issues/call-picture-over-the-whole-glass.md.

## Through a Raspberry Pi

A D1001 and a Guition 10.1 in a video call in both directions, through a Home Assistant Yellow (three calls of 36 s, 2026-11-10): 8.3 to
9.5 pictures a second over the whole call and about 9.8 once it runs, 31 KB and 13 KB a picture, sound waiting 5 to 50 ms on its way and
never running dry. The app used about 40 % of the Yellow while it ran. With pictures of 960 pixels a side the same call reached 6 to 8.
