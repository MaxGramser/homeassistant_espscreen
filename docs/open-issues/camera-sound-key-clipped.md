# The full view's sound key showed as a quarter, once

## The symptom
On a reTerminal D1001 (dev firmware of 2026-11-03 with the PPA guard's scaled rule, main app 0.4.93), a camera opened
full screen from its live tile on a page of four live tiles. The stream took long to come, and when it did the sound
key at the right of the top bar showed only its bottom right quarter: the round edges at the right and the bottom, a
straight cut through its middle at the left and the top, the glyph's left part visible. Seen once by the owner (a
photo); the next openings drew the key whole.

## What we know
- The opening's log: "stream 0 into 1280x715 at 0,85 from the app's stream, turned 270", "picture 288x512 for
  1248x702 at 16,91, scale 39", "first picture on the glass 4962 ms after it started (connected after 81, the app
  answered after 97, its first bytes after 97)", "live 5040 ms after it started". The app's log: "first picture 5.1 s
  after the link went out; its source: offer 0.0 s, answer 4.6 s": Home Assistant's WebRTC answer for that camera took
  4.6 s. The sound came with the live stream ("camera holds the speaker").
- The key is made at the sound's event (`runtime_tiles::camera_sound_show`), after the loader's spinner has gone at
  LIVE (c73d863e), at `detail_bar::right_slot(camera_root)`: 60 px at the glass's top right, rows 16 to 76, above the
  stream's room (y 85 on). The spinner is 30 px, placed in the middle of that slot: the quarter that showed is not the
  spinner's place (that would be the middle), it is the key's bottom right.
- Nothing of the stream's picture lies in the bar: the spot kept from LVGL (`glass_core.cpp` keep_out) is the picture's
  rectangle, 16,91 to 1264,793.
- The PPA guard's change of the same day leaves a turned copy at its own size exactly as before (`ppa_guard.h`): the
  bar's flushes are such copies.

## Ruled out
Nothing yet: it came once, in the one opening whose stream was 5 s late.

## Candidates
- A race between the key's first draw and the stream's first copies: the key is invalidated while the room is armed
  and the first live picture is laid onto the glass; the kept pieces of LVGL's area, or the flush of them, lose a part.
- The spinner's hide and the key's creation in one frame, their areas joined, cut against a spot told late (`spot_told`,
  `follow`).

## The deciding experiment
Open the view with a camera whose WebRTC answer is slow (or hold the app's first picture back a few seconds in
live_stream.py) on the bench D1001, with the serial log; the moment the key appears, `esphome.<node>_ui_snapshot`
(what LVGL has) and `esphome.<node>_glass_snapshot` (what the panel shows), `diagnostics/capture_ui.py`. LVGL's
picture whole and the panel's a quarter: the stream's copy; both a quarter: the keep-out's cut.

## Pointers
`runtime_tiles.h` camera_sound_show, camera_warm; `detail_bar.h` right_slot; `glass_core.cpp` keep_out, place,
follow; `live_view.cpp` show (the full view's branch).
