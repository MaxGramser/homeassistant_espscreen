# The preview shows when a script last ran in UTC

## The symptom

A script, scene or automation tile says when it last ran ("Last 05:16", "Yesterday 22:22"). In the editor's Preview
and on its pages the same tile says 04:16 and 21:22 where the screen says 05:16 and 22:22: the preview shows the
moment in UTC, the screen in its own time zone. The clock in the preview's top bar is right.

## What we know

Seen on 2026-11-24 on the app of 0.4.102, in a home on UTC+1: a screen's glass read back over the API beside the
Preview of the same page, one hour apart on both tiles of the page that show a last run. It is not new: the code is
the same on the release before.

The firmware turns the moment into a clock time with `ESPTime::from_epoch_local` (`tile_words_lvgl.h`,
`last_run_text`). On a screen that is ESPHome's own, which knows the zone. In the preview it is the stand-in of
`host_shims.h`, which uses `gmtime`. The preview is told the browser's offset (`_preview_time` in
`FirmwarePreview.vue`, `utc_offset` in `web/wasm/firmware_preview.cpp`) and adds it by hand for "now" only, so every
other moment the firmware makes local stays in UTC.

## Ruled out

- The app or Home Assistant sending another moment: the screen and the preview get the same seconds since 1970.

## Candidates

1. One place instead of two: the stand-in's `from_epoch_local` adds the offset the preview was given, and
   `firmware_preview.cpp` stops adding it for "now" itself. Every moment the firmware makes local is then right in
   the preview, also the ones nobody has looked at yet (a calendar's times, a countdown's end, a forecast's hours).

## The deciding experiment

A preview test (`web/wasm/test.sh`) that gives the preview an offset and a script tile with a last run, and reads the
text: it fails today and passes with candidate 1. Then look at a calendar tile and a week forecast in the preview
beside a screen, in a browser that is not on UTC.

## Pointers

- `components/smart_display/host_shims.h`: `ESPTime::from_epoch_local`.
- `web/wasm/firmware_preview.cpp`: `utc_offset`, the clock's `now`.
- `components/smart_display/tile_words_lvgl.h`: `last_run_text`.
