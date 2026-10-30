# The governor may squeeze the work that holds its main loop up

## The symptom
A screen whose main loop is held up ("took a long time" from a component) raises the governor's step for the
SLOW_LOOP sign, and the step squeezes the own camera's video, sensing, the background and the live tiles. When the
work that held the loop up is a full view, the video encoder or the sound, the squeeze can slow the very stream the
person is in. Seen on a reTerminal D1001 right after a boot (2026-10-29, 19:48): "live tiles 1/2, own camera 1/4,
sensing 1/2, background 1/2 (the main loop held up)"; on a Guition 10.1 in a full view: "ui_refresh took a long time
for an operation (53 ms), max is 50 ms" beside "laying out 56 to 60 ms a picture" (21:45).

## What we know
pressure.h: the step table gives OWN_CAMERA 1 at step 1 and 2 at steps 2 and 3, and SLOW_LOOP raises the step like
any other sign. Since 564282e2 the own camera stays whole while someone hears the screen's microphone (a call), so the
video of a call is no longer squeezed by any step. The live tiles and sensing still follow the steps. A full view
lays its pictures out on the main loop, which is where the slow-loop sign comes from.

## Ruled out
The full view pausing for the governor: pace() runs only for tiles (live_view.cpp), so a full view is never paused.

## Candidates
- A slow loop caused by the live view's own layout counted as a sign at all.
- The full view's layout off the main loop, so it cannot hold it up.

## The deciding experiment
The number of SLOW_LOOP signs a minute (the governor's `signs()`) with a full view open, against the same page without
it; if the full view brings the signs, the step it raises is the loop's own doing.

## Pointers
components/smart_display/pressure.h (STEPS, `signal`, `level`, `heard`), live_view.cpp (pace, the full view's layout),
ESPHome's component "took a long time" warning, the Pressure sensor of a screen in Home Assistant.
