# Pictures fetched ahead on a tight store: proven on the host, not yet on a 7-inch

## The symptom

On a board whose picture store is small for its pictures (a Waveshare ESP32-S3-Touch-LCD-7B: 1046 KB), two large
pictures on two pages out of sight (a 3x4 plugin photo of 713 KB, a 2x4 map of 478 KB) were fetched again and again,
every second or two while the screen was awake, each one letting the other go (GitHub #415, 2026-11-12).

## What we know

- The cause was two rules about the same room that did not know of each other: fetching ahead while the store was under
  three quarters of its budget, without counting the picture about to come, and letting a page out of sight's picture
  go once the store was over its budget.
- Since 2026-11-24 on dev a picture fetched ahead uses spare room only (`picture_store` `fits_ahead`, the loader's
  `room_ahead`, the arrival in `picture_done`). tests/test_pictures_ahead.cpp runs the issue's numbers through the real
  loader and store: without the rule 120 downloads and 119 pictures let go in a minute, with it one download and nothing
  let go; two pictures that fit together both come.

## Ruled out

- A camera on a kept page: never fetched ahead, before or after.

## The deciding experiment

A 7B (or any board with a store of about 1 MB) on a page without pictures, two pages with the issue's tiles: with Debug
mode on, the log shows each picture asked for at most once while the screen stays awake, and no "frees (over the
budget, from a page out of sight)". Turning to each page shows its picture (the one that did not fit arrives then).
None of the home test screens has a store this small; the reporter offered to test.

## Pointers

`components/smart_display/picture_store.h` (`bytes_of`, `ahead_level`, `fits_ahead`), `picture_loader.h`
(`room_ahead`, `loading_rank`), `picture_rounds_lvgl.h` (`loader_bind`, `picture_done`, `tile_picture_want`),
`camera_view.h` (`pictures_ahead`), docs/KEPT_PAGES.md.
