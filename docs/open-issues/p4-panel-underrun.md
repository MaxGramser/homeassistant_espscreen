# A real underrun of the panel on an ESP32-P4

The frame of blue that no counter saw is solved: it was a missed restart of the panel's DMA (docs/CAMERA.md, "A frame's
restart"). This note is about the other flash, the one the screen does count.

## The symptom

Now and then the whole glass gives one bright flash and settles straight back. The screen records it: the sensor "Panel
misses" goes up by one, "Panel watch" reports one flash and one dry frame, and the governor steps down for about ten
seconds ("the panel ran dry"). GitHub #379 reports about twelve a day on a reTerminal D1001 with no camera in use.

## What is known

- The DSI bridge fetches the frame buffer from PSRAM line by line. A fetch held up for more than 40 to 80 microseconds
  runs its FIFO dry; the bridge raises its underrun flag, drops the rest of the frame and the panel shows its colour for
  no data.
- The flag is read at every frame (`glass_dsi.cpp`, `frame_seen`), since 2026-10-29 with the mask off, so every underrun
  counts.
- The DMA repeating its frame by itself does not prevent this and does not make it worse. A forced underrun on a
  picture of stripes (2026-11-08, 98 counted in 30 s, a bare firmware on a D1001) still showed and counted, and left
  the picture in its place.
- The panel's bandwidth matters. A reTerminal D1001 pulls a third to a half more from PSRAM than a Guition 10.1 for the
  same picture, and a pixel clock of 70 MHz instead of 80 made flashes rarer.

## Ruled out

- The DSI host's line rounding: a porch that makes the line a whole number of byte clocks changed nothing.
- Wi-Fi signal: both boards at -26 to -39 dBm.

## Candidates

1. Something on the PSRAM bus holding the bridge up: the encoder, the camera's frames, the JPEG decoder, the PPA, the
   Wi-Fi chip's SDIO buffers. #379 has no camera in use, which narrows it to the rest.
2. A write-back of the cache or a long critical section that stalls the bus in the same way.

## The experiment that decides

It was not reproduced on the bench: 5,700 tile updates on a D1001 standing up in dark mode gave no miss. First find a
load that brings it. Then take away one consumer of the PSRAM at a time with the pixel clock kept, and see which one ends
it. The log line of a miss says who held the glass and whether LVGL was flushing.

## Pointers

- `components/smart_display/glass_dsi.cpp`: the panel watch, the underrun mask.
- `components/smart_display/pressure.h`: the governor.
- `packages/boards/reterminald1001.yaml`: the pixel clock and the porch, with the arithmetic.
