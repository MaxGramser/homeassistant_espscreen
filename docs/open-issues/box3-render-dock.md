# The host render of the ESP32-S3-BOX-3 fails on the dock, while the board's own glass does not

## The symptom
`tools/render/run.py esp32s3box3` fails both ways up (2026-10-31, box3 branch at 32dd0eed, on upstream dev 09f23546):

- Lying down, the self test reports `GEOMETRY FAIL clickable=(27,255)-(294,275)`: something you can tap at y 255 to
  275, below the 240 px glass.
- The dock check: page 1 looks different after a tap above the drawer closed it, and "a drag down never closed the
  drawer: nothing after 6 s".

## What we know
On a real BOX-3 (GT911 unit, the same board file) the dock opens with a swipe up from the bottom edge, shows the pages,
and closes both with a tap above it and with a drag down, lying down and standing up (2026-11-01). The BOX-3 is the
first board with 320 x 240 glass and PSRAM with 16 MB flash, so it is the first small glass to get everything the
larger boards get (docs/MODULES.md). The CYD has the same 320 x 240 glass without them.

## Ruled out
The board's hardware: the render runs the shared firmware on the host, without the board's display or touch drivers,
and the real unit does not show the fault.

## Candidates
- A module or overlay that only the larger boards get places its clickable for a taller glass, and the self test
  finds it below the 240 px edge. The dock's checks then fail because that overlay sits over the drawer.
- The render harness's dock check assumes a drawer height that 240 px of glass does not leave.

## The deciding experiment
Render the CYD (`tools/render/run.py cyd cyd-portrait`) on the same commit. If it passes, the fault comes with the
full tier on small glass: find the object at (27,255)-(294,275) in the self test's tree and the module that makes it.
If it fails the same way, the fault is in the harness's dock check on 320 x 240.

## Pointers
tools/render/run.py, components/smart_display/modules.py, docs/MODULES.md, docs/ESP32S3BOX3.md.
