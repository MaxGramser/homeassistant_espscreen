# A tile of the screen's own camera costs 50 to 60 ms of the PPA a frame

## The symptom

A tile of the screen's own camera shows at most every second frame of a 30 fps camera, and beside other live tiles or
a video viewer it falls to 8 to 10 pictures a second or fewer. Four tiles that nearly fill the glass show 4 to 6.6
pictures a second on the camera's tile and 2.3 to 4.5 on the others.

## What is known (reTerminal D1001, chip revision 1.3, 2026-11-09)

- The copy of a 1280 x 720 YUV420 frame into a 240 x 135 tile takes 50 to 60 ms on the PPA, on the camera's task, with
  the glass held. The camera delivers a frame every 33 ms, so the tile takes every second one: 15 a second when alone.
- It is the PPA and not the network: the live tiles stay at about 5 a second beside it with a limit of 20 and pictures
  of 19 KB, and go to 8 to 10 a second without it. The time all tiles spend on the PPA adds up to about a second a second.
- The video viewer got 11 to 12 frames a second with the tile at 15, against 14 to 15 with the tile at 1.5.

## Ruled out

- Bursts of 128 bytes instead of 64: 47.5 ms against 52.6 ms, not enough to take every frame.
- Letting go of the glass during the copy: 9.2 pictures a second against 8 on this tile, nothing on the others.

## Candidates

- The input's pixels: the PPA reads the whole frame to bring it down to a small tile.
- The guard's pieces, each with its cache write-back.

## The experiment that decides

The same copy with an input cut half as large, and the number of pieces the guard cuts it in on revision 1.3. If the
time follows the pieces the lever is in the guard; if it follows the input, only a smaller source helps, which is a
change to the plugin API.

## Pointers

`own_frame` in `components/smart_display/live_view.cpp`, `hw::OWN_TILE_PPS`, `docs/PLATFORM_PLAN.md` 4.11.
