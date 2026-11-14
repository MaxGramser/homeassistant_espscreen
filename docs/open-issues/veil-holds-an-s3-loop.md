# The veil holds an ESP32-S3's main loop for about 60 ms

## The symptom
On a Guition 4-inch (ESP32-S3, RGB panel, 480 x 480) every alert that showed or closed came with "interval took a long
time for an operation (58 ms), max is 50 ms" and "lvgl took a long time", and the governor stepped down for a few
seconds ("own camera 1/2, sensing 1/2, background 1/2 (the main loop held up)"), 2026-11-10. On a reTerminal D1001
(ESP32-P4, 800 x 1280) the same veil takes 36 ms and raises nothing.

## What we know
`glass::veil` (docs/MOTION.md) darkens the frame buffer on the main loop in one call, four passes over the glass. On the
P4 the time is the memory's: one core or two, 36 ms. The S3 run was read from a log at WARN level only, so whether the
60 ms is the veil itself, the card drawn before it (`screen_motion::show` draws it at once) or both is not measured,
and nobody looked at the glass during it.

## Ruled out
Nothing yet.

## Candidates
- The veil over PSRAM at the S3's speed, a quarter of the pixels of the P4 but a far slower bus.
- The card's own drawing at once, which is in the same loop turn.
- The veil in steps over a few loop turns (a pass a turn) would end the warning either way, at the cost of a dim that
  takes longer.

## The deciding experiment
Log the veil's time at INFO on an S3 with an RGB panel (it is at DEBUG) and the time of `lv_refr_now` before it, for an
alert on a full page. If the veil alone is over 50 ms, split it into a pass a loop turn on boards where one call
exceeds the loop's limit, and look at the glass.

## Pointers
`components/smart_display/glass_core.cpp` (`veil`), `screen_motion.h` (`show`, `hide`), `pressure.h` (SLOW_LOOP),
docs/open-issues/governor-slow-loop-feedback.md.
