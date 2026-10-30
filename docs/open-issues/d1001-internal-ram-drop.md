# The reTerminal D1001's internal RAM drops while the encoder and sensing run

## The symptom
Free internal RAM 284 KB after boot at 19:48, 140 KB at 20:06 (2026-10-29), largest block 49 then 40 KB, with the
H.264 encoder streaming to another screen and Screen camera's light level and motion sensing on. With the video to
the 10.1 running it stayed around 143 KB; without, 284 KB.

## What we know
The encoder holds about 78 KB of internal RAM (its report line), and screen_video skips frames below INTERNAL_LOW.
The drop may be the encoder's and the viewers' buffers taken once and kept (then it is a level, not a leak), or
sensing's frames. Nobody measured whether it stops falling.

## Next step
Heap watch over an hour with the encoder on and sensing off, then sensing on: a level that holds is fine, a slope is
a leak. heap_watch's "Lowest" line at the next boot says where it ended.

## Pointers
components/smart_display/heap_watch.*, the screen_video report line ("bytes of internal RAM free, N held by the
encoder"), HA sensors heap_free and heap_largest_block.
