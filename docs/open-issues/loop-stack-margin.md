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

On main (0.4.97) the sensor cherry-picks cleanly; the fix does not (dev has ops main lacks) but applies as the same
mechanical change to main's own page_receiver.cpp: 9.5 KB on the P4 and the S3, 8.1 KB on the CYD. It goes with the next
release instead of a hotfix (2026-11-16).

## Ruled out

- The live stream's decode: it runs in the stream's own task, not on the loop (its log line just stood before the
  overflow).
- A stack in PSRAM for the loop task: ESP-IDF asserts that the stack is internal whenever the cache is off
  (`esp_mmu_map`, OTA's mmap), on the P4 and the S3.

## Readings on boards (2026-11-16)

"Loop Stack Free" in bytes, the low mark since boot, each board with its everyday layout:

| Board | Before the fix | After b8e887c6 |
|---|---|---|
| Guition 10.1 (ESP32-P4), seven pages, 54 tiles, three plugins (a camera with video, a voice assistant, a Bluetooth proxy) | 40 after a layout's commit, then a stack overflow when a page of five camera tiles opened | 10,796 after the commit; 10,268 with that page open (four tiles live at 7 to 8.6 pictures a second each, no restart, no panel misses); 9,976 with Home Assistant asking for the screen's own video nine times beside the four streams |
| Guition 4 inch (ESP32-S3, RGB panel) | 1,234 (firmware e2e114b9, the sensor without the fix) | 10,130 |
| CYD (ESP32, no PSRAM) | not read on the board; about 13.2 KB deep by the compiler's sums | 10,507 |

The deepest any board went after the fix is about 6.4 KB of 16 KB, LVGL's own depth included; nothing reads under 4 KB,
so the stack stays 16 KB. The S3 was at 1.2 KB with an ordinary layout before, on a chip with no hardware guard: the
risk was not the P4's alone.

## Candidates

- The screensaver's build: the saver op calls `saver_changed`, which may build the screensaver on top of the op's
  1,152-byte frame inside the API's call.

## The deciding experiment

Still to read on the same three boards: the low mark after the screensaver has come (the saver op's build, above) and
after a night of use. At least 4 KB left on each: the 16 KB stays and this file is solved. Less: `loop_task_stack_size`
is sized from that reading for that chip (32 KB is ESPHome's ceiling), and a budget in `tools/stack_chains.py
--budget` goes into the checks.

## Pointers

`components/smart_display/page_receiver.cpp` (receive), `loop_stack.h`, `packages/core.yaml` (show_tile_page_soon,
open_page, go_home, Loop Stack Free), `packages/hardware/esp-idf.yaml`, `tools/stack_chains.py`, docs/ARCHITECTURE.md
"The loop's stack".
