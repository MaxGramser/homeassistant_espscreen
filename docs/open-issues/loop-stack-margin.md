# The loop task's stack: how much is left on a board with its largest layout

## The symptom

On a Guition 10.1 (ESP32-P4) with a large layout (six pages, sections, about 45 tiles, a live camera tile) the health
line said "layout applied, loop_stack_min_free=300" and later 152, of a 16 KB stack. With three plugins and a seventh
page of five camera tiles it said 40, and opening that page from Home Assistant ended in "A stack overflow in task
loopTask has been detected" (2026-11-16, 20:56). The P4's hardware stack guard caught it; an S3 or a classic ESP32 has
no such guard, so the same depth there would corrupt memory without a word.

## What we know

- The figure is in bytes: `StackType_t` is `uint8_t` on ESP-IDF, RISC-V and Xtensa alike.
- From the compiler's frame sizes (`tools/stack_chains.py`, ESPHome 2026.9.0), dev before the fix: the message parser,
  `receive`'s lambda, was one frame of 9,456 bytes on the P4 (9,424 on the S3; main 0.4.97: 8,240), and a layout's
  commit built its page and cards on top of it inside the API's call. That chain summed to about 16.1 KB on the P4,
  which matches the board's 40 bytes left. A state message for a cover on a cover group page went 15.0 KB deep on the
  S3. On the CYD the parser was 7,008 bytes, a message's deepest path 11.6 KB, a commit with its page about 13.2 KB.
- After the fix (each op its own `noinline` function, a tile's Extra on the heap, pages built from the loop's next
  pass): a message's deepest path is 9.7 KB on the P4 and the S3 and 8.2 KB on the CYD; a page built from the loop is
  5.9, 5.7 and 5.6 KB.
- None of these sums holds LVGL's own depth: LVGL is C and is compiled without the flags. A live tile's name is drawn
  off the glass with `lv_snapshot_take`, which runs LVGL's software draw on the loop's stack, and LVGL's layout and
  redraw recurse once per level of the object tree.
- main (0.4.97) has the same design at about 14.9 KB of 16 KB by statics with a large layout on a P4, unproven on a
  board.

## Ruled out

- The live stream's decode: it runs in the stream's own task, not on the loop (its log line just stood before the
  overflow).
- A stack in PSRAM for the loop task: ESP-IDF asserts that the stack is internal whenever the cache is off
  (`esp_mmu_map`, OTA's mmap), on the P4 and the S3.

## Candidates

- LVGL's draw depth under a page of live tiles is what is left between 9.7 KB and the end; a reading decides it.
- The screensaver's build: the saver op calls `saver_changed`, which may build the screensaver on top of the op's
  1,152-byte frame inside the API's call.

## The deciding experiment

The home Guition 10.1, the 4-inch Guition (S3) and the CYD, each with its largest layout (on the 10.1 the three
plugins and the page of four live tiles), read "Loop Stack Free" in Home Assistant (firmware e2e114b9+) before the fix
and after it, after a layout lands, a page of live tiles opens and the screensaver comes. At least 4 KB left on each:
the 16 KB stays. Less: `loop_task_stack_size` is sized from that reading for that chip (32 KB is ESPHome's ceiling),
and a budget in `tools/stack_chains.py --budget` goes into the checks.

## Pointers

`components/smart_display/page_receiver.cpp` (receive), `loop_stack.h`, `packages/core.yaml` (show_tile_page_soon,
open_page, go_home, Loop Stack Free), `packages/hardware/esp-idf.yaml`, `tools/stack_chains.py`, docs/ARCHITECTURE.md
"The loop's stack".
