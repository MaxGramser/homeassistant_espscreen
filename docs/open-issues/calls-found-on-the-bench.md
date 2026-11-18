# Calls: what a day on two boards left open

A Guition JC8012P4A1 V3 and a reTerminal D1001 in calls with each other through the app, with echo cancelling new on
both (2026-11-17). The echo itself is in docs/P4_AUDIO.md; these are the things seen on the way that have no fix yet.

## The first call after a restart can stall

Twice the first call after the boards had restarted (a firmware update each time) lost its media after a few seconds:
the screen logged "the stream went quiet" and its voice's "the add-on went away (errno 11)", and the app counted 2.2
and 4.4 s of voice from that screen in calls of 12 and 20 s, with 0 to 3 pictures. Eight calls in a row after that
(four with video) ran whole, 7 to 8 pictures a second each way. The app's own CPU was idle. Its log has "Retrying
screen sync (TimeoutError)" in the same minutes. Candidates: the app still delivering the layout to a screen that just
said hello, on the same connection to Home Assistant the call's messages need; the screen's own video server starting.
The experiment: restart a board, call within ten seconds, and read which of the app's tasks waits.

Seen a third time on 2026-11-18, after a firmware update of the Guition alone (the audio stack's pin moved, dev
fdc61b84), with the first call made about five minutes after it had started again, so not only within seconds: the app
counted 13.5 s of voice from the Guition in a call of 26 s and logged "Retrying screen sync (TimeoutError)". The
Guition did not restart and kept its connection to Home Assistant, but its hang-up key seemed dead for a while; when
it took the tap, the call's card said "Not reachable", because the app no longer held the call. The screen stayed in
the call and asked for the call's picture every 20 s until then ("camera.tessera_call is not on the layout" in the
app's log). The second call, minutes later, ran whole for half a minute: 7.5 to 8 pictures a second, sound that never
ran dry, the canceller Enabled, sound heard well at both ends. New to explain: why the screen's own keys did not
answer during the stall, and why it did not leave the call by itself when its stream went quiet.

## A sound takes about a second there and back

With a computer as the far end (docs/CALLS.md, "Measuring a call from a desk"), what the computer sent came back from
the screen's microphone 1.0 to 1.1 s later, the canceller at rest, on both boards. That is the screen's sound buffer on
the way in (`live_view.h`, a run-up of 200 ms and up to a second held), the speaker's own buffer, the room, and the
400 ms the voice may wait on its way out (`talk_uplink.h`). Not split yet into the way in and the way out; a call
through the app adds its own on top. Under a second for the whole way is what the owner asked for a call.

## The canceller needs time after it was thrown off

Two boards in a call with each other on one desk hear each other's speaker. After eight such calls the Guition's
canceller took 5 dB away in the next measurement, then 11, 16, 24 and 23 in the four after it, 33 s each: it learns
the room again in about a minute of far-end speech. Two rooms do not do this. At the canceller's level `normal` what is
left shows; at `aggressive` the library presses it down and takes more of a voice that speaks at the same time
(docs/P4_AUDIO.md). The levels are not yet compared in one call (`call_bench`'s `nl`).

## The Guition's microphone is noisy at the far end

Silence from the Guition reads -37 to -47 dBFS at the far end, from the D1001 -56 dBFS, with a voice beside each at
about -22 dBFS: the Guition's microphone needs 24 dB more gain for the same voice, and its noise comes up with it.
ESP-SR has noise suppression (its AFE, not the plain AEC this project uses); untried.

## A live view aborts where it should give up

A page with four live camera tiles, opened and left four times in ten seconds on a Guition 10.1 that also ran the
camera's video, the wake word and Bluetooth: the internal RAM fell to 38 KB, an allocation of 28,801 bytes failed in
the task `live_view`, and the firmware called abort() there (2026-11-17 08:01). The streams of the page left were
still closing while the next ones opened. A stream that cannot get its memory should end as failed, as its other
refusals do; which allocation aborts is not found yet (the address is in the screen's abort record).

## One message of the old protocol leaves a screen saying "Configuration problem"

A `screen_message` with `v` 1 sent by hand to a screen on protocol 2 put "Configuration problem. Update the add-on."
on the glass, and it stayed there until the screen restarted: the app believed the screen was in step and sent nothing
that would clear it. Only someone who can call the screen's action in Home Assistant reaches this.
