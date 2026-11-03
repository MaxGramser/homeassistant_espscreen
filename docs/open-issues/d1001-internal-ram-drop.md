# The reTerminal D1001's internal RAM drops while the encoder and sensing run

## The symptom
Free internal RAM 284 KB after boot at 19:48, 140 KB at 20:06 (2026-10-29), largest block 49 then 40 KB, with the
H.264 encoder streaming to another screen and Screen camera's light level and motion sensing on. With the video to
the 10.1 running it stayed around 143 KB; without, 284 KB.

## What we know
The encoder holds about 78 KB of internal RAM (its report line), and screen_video skips frames below INTERNAL_LOW.
Measured once a minute through the evening of 2026-10-29 (Home Assistant's heap_free and heap_largest_block):

| Time | What the screen did | Free | Largest block |
|---|---|---|---|
| after a boot | nothing watched yet | 284 KB | 192 KB |
| 20:06 to 20:46 | five camera tiles on its page, its video to another screen with sound | 140 to 144 KB, flat | 40 KB |
| 20:49 to 21:00 | one camera tile on its page, its video with sound | 214 to 223 KB, flat | 100 KB |

Each level held for as long as the work stayed the same: over 40 minutes at 140 to 144 KB there is no slope, so it is
a level taken by the work (the encoder, the stream's sound, each live tile's buffers), not a leak. Once taken it was
not given back while the screen ran: from 20:05 to 20:30 nobody pulled the video and the level stayed at 140 KB.

## Ruled out
A leak in sensing or the encoder over the measured hour: the levels stay flat.

## Candidates
The fragmentation is the open point: a largest block of 40 KB beside five live tiles and the video leaves little for
the next large allocation of internal RAM (a sixth stream, a TLS session).

## The deciding experiment
The same page and video for a few hours, and heap_watch's "Lowest" line at the next boot: a largest block that stays
at 40 KB is a level; one that shrinks further is fragmentation growing.

## Pointers
components/smart_display/heap_watch.*, the screen_video report line ("bytes of internal RAM free, N held by the
encoder"), HA sensors heap_free and heap_largest_block.
