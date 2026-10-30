# How the firmware is put together

One page, one map. It says which layers the firmware has, what each one knows and does not know, where its code
lives, and which rules hold between them. Everything here is current as of 2026-10-28 (branch dev); every section
points to the document that has the detail and to the test that proves it. Read this first, then the document of the
thing you change, then the head of its file, then its test.

The product has four parts (AGENTS.md): the firmware (`packages/` and `components/smart_display/`), the boards
(`boards.yaml`, `packages/boards/`), the add-on (`screen_manager/`) and the editor (`web/`). This page is the
firmware's map, with the add-on where the firmware's layers end at it.

## The layers, from the panel up

```
  Home Assistant ──── add-on (screen_manager) ──── editor (web)
                          │  pictures, streams, layouts, events, the hello
                          ▼
  ┌──────────────────────────────────────────────────────────────┐
  │ runtime_tiles.h: the binder (pages, tiles, cards, the loop)   │
  │   picture_loader / picture_question / picture_fetch           │
  │   live_spots ── live_view (streams: Source + shared draw)      │
  │   pressure (the governor)   audio_owner   header_bar   plugins │
  ├──────────────────────────────────────────────────────────────┤
  │ hw::caps: what this screen can do, one record                  │
  ├──────────────────────────────────────────────────────────────┤
  │ picture_engine (per chip)       glass (per panel kind)        │
  │   P4: JPEG + PPA, ppa_guard      DSI (P4)   RGB (S3)          │
  │   S3: esp_new_jpeg, CPU blit     core: the lock, the rooms    │
  │   other: BMP rows, no blit       other: no direct glass        │
  ├──────────────────────────────────────────────────────────────┤
  │ ESPHome + ESP-IDF: LVGL, the display, Wi-Fi, the API, audio    │
  └──────────────────────────────────────────────────────────────┘
```

A layer talks only to the one beside it. The streams never touch the panel's driver, the engine never knows a socket,
the governor never knows a pixel, and nothing in the shared code reads a board's name, a chip or a pin.

### 1. The build decides the engine, the glass and the streams

`engine_build.py` is one table keyed by chip and by what the build has (LVGL, PSRAM), never by board. It gives a build
three defines, each with its own files, and one may come without the others:

| define | what it is | files |
|---|---|---|
| `PICTURE_ENGINE_P4` | the ESP32-P4's hardware JPEG decoder and PPA (scale, turn, copy) | `picture_engine_p4.cpp`, `ppa_guard.cpp`, `ppa_trace.h` |
| `PICTURE_ENGINE_S3` | Espressif's software decoder esp_new_jpeg on an ESP32-S3 with PSRAM, a CPU blit as-is | `picture_engine_s3.cpp` |
| `GLASS_DSI` / `GLASS_RGB` | a frame buffer a task may write past LVGL | `glass_dsi.cpp`, `glass_rgb.cpp`, shared `glass_core.cpp` |
| `USE_LIVE_VIEW` | the streams | `live_view.cpp` |

Without an engine a screen decodes BMP rows (`picture_fetch`) and LVGL draws every still; without a direct glass there
are no streams. A new chip or panel kind is a row in that table with files of its own; `picture_fetch`, `live_view`,
`live_spots` and `runtime_tiles` do not change for it. Detail: docs/PICTURE_ARCHITECTURE.md section 3.9;
test: `tests/test_live_view.py`.

Modules work the same way one level up: `modules.py` gates the parts of the UI a 4 MB board has no room for behind a
define per module (docs/MODULES.md).

### 2. The glass: the panel as a surface

`glass.h` is what the panel is as ESP-IDF made it (size, pixel format, turn), the frame buffer, one lock and the rooms
LVGL keeps out of while a stream writes there. The glass knows nothing of pictures, streams or decoders.

The lock means two things at once, and both matter:

- **One writer at a time.** LVGL holds it for each refresh (REFR_START to REFR_READY); a stream's task holds it for each
  decode and each copy. Without it a stream's first picture landed under LVGL's last still (2026-10-12).
- **One user of the 2D-DMA at a time.** On a P4 the JPEG decoder, the PPA and LVGL's own turned strips all share the
  2D-DMA, and two of them from different tasks is what hangs the chip (espressif/esp-idf #18999, #19108, #19096).

On DSI the glass counts the panel running dry (`glass::misses`, the "Panel misses" sensor), with the chip's mask on
that flag taken off (ESP-IDF masks underruns in the first lines of a frame, the ones that blue the whole glass), in the
panel's own callback at each frame's end: the panel watch, which notes for each flash who held the glass and says each
minute in the "Panel watch" sensor (`glass::watch_said`), so a flash needs no eye on the glass. The runtime only tells
it what the glass cannot see (log lines, the finger: `glass::note_log_line`, `note_finger`); an RGB
panel's driver keeps no such count, so on an S3 a frame that shifts sideways is seen by eye only. Detail: docs/PICTURE_ARCHITECTURE.md 3.1, docs/CAMERA.md "Live on
the P4 boards" and "Live on an ESP32-S3"; tests: `tests/test_live_view.cpp` (a rectangle on a turned panel).

### 3. The picture engine: decode, scale, turn

`picture_engine.h` turns bytes into pixels and pixels into other pixels, and says which formats this screen's decoder
takes. It owns every chip fact: the PPA's units, its macro block, the FIFO size and the turned block the hardware never
finishes (DIG-734), which `ppa_guard` cuts into pieces the hardware takes whole; the S3 decoder's memory, taken from
PSRAM first through linker wraps. Its `Limits` say what the chip affords: picture sizes, live tiles at once (P4 four,
S3 one), whether a decode may run under the glass lock, the full view's pictures a second, the tile budget (P4 24,
S3 8, shared as `tile_pps = clamp(budget / tiles, 2, 6)`) and which core the streams decode on (P4 1, S3 0).

The rule the app and the engine agree on: **the app sends a live tile's picture at its card's size and turned as the
glass is** (the hello's `picture_turn`, each picture's `X-Turn`), so an engine never scales or turns for a tile. The P4
only turns what is left between picture and glass; the S3 copies as-is. Detail: docs/PICTURE_ARCHITECTURE.md 3.2,
docs/PLATFORM_PLAN.md 3.2, 4.7 and 4.12; tests: `tests/test_picture_engine.cpp`, `tests/test_ppa_guard.cpp`,
`tests/test_ppa_trace.cpp`.

On a P4 every PPA call, the firmware's, LVGL's and a plugin's, passes the guard through the linker's wrap, is noted in
a ring that survives a restart (`ppa_trace.h`), and a copy that never comes back ends the boot by name within three
seconds from a watch task of its own, since nothing brings the engine back without a restart.

### 4. The streams: live_view and live_spots

`live_view.cpp` runs one task per stream (the full view, each live tile, a plugin's live place), owned by the main loop:
`open()` makes it, `close()` and `tick()` end it. Two halves:

- **Source**: where the pictures come from. The app's pull link, one picture per request (a live tile, since 2026-10-28);
  the app's multipart stream with sound (the full view, and a tile of an app before the pull link); the screen's own
  camera's frames (a tile of it, plugin API 0.22, no encoder on the way).
- **The shared draw path**: decode with the engine, lay out (a full view scaled to its room; a tile's corners, shade and
  name as one overlay made once per stream), copy onto the glass under the lock, only while nobody stopped the stream.

A live tile is paced by time (`pace`, never by skipping decodes: the link is pull-driven, so skipping only pulls faster),
at most `hw::LIVE_TILE_PPS` (6) a second, less on a busy screen. The full view shows the newest picture and uses the
sound as its clock. A stream's task runs at priority 2, below the wake word (3), and takes the writers' priority (5)
only while it holds the glass.

`live_spots.h` is the machine that decides, every round, which tile or plugin place may stream (its card on the glass,
the page clear, nothing over it), asks the app in turn, opens, stops when covered, gives up after its tries. The full
view's stream is not a spot: it is the loader's answer, and it opens once the page's streams have ended
(`live_view::ending`), never beside them: one connection at a time, as an S3 has internal RAM for one. Detail: docs/CAMERA.md "Live on the P4 boards", "A live
picture on a camera tile", docs/PICTURE_ARCHITECTURE.md 3.4 and 3.5; tests: `tests/test_live_view.cpp`,
`tests/test_live_spots.cpp`.

### 5. Pictures: one question, one loader, one download task

Every picture a screen shows goes one way. `picture_question.h` is the one shape of a request (who asks, of what, which
size and places, how painted, which formats, whether it may stream); `picture_loader.h` decides the order (an alert
first, the full view, a card, the library, the tiles on the glass, last what is fetched ahead); `picture_fetch.h` downloads
in a task beside the main loop and decodes a BMP as it streams; `camera_view.h` keeps the rhythm (a still every four
seconds, never a queue). The add-on answers every question the same way (`screen_manager/app/picture_service.py`).
Detail: docs/PICTURES.md, docs/CAMERA.md "One route for every picture"; tests: `tests/test_picture_question.cpp`,
`tests/test_picture_loader.cpp`, `tests/test_picture_fetch.cpp`, `tests/test_camera_view.cpp`.

### 6. The capability record

`hw.h` holds what this screen can do in one record, `hw::caps()`: live video, speaker, microphone, echo cancellation, a
camera of its own, live tiles at once, the heaps. The build's half comes from the configuration (`hw_build.py` defines
`HW_*` when a component of that kind is built in); the boot's half from the running screen (the engine's limits,
`live_view::available`, the memory). The firmware, the hello to the app, the editor and the plugins all read this one
record, so nothing infers a capability from a board. Detail: docs/PLATFORM_PLAN.md 3.3; tests: `tests/test_hw.cpp`,
`tests/test_hw.py`.

### 7. The governor

`pressure.h` is what a busy screen gives up first, so the glass and the voice never do. The order, from what never
waits to what waits first:

```
GLASS > VOICE > DOORBELL > LIVE_TILES > OWN_CAMERA > SENSING > BACKGROUND
```

Signs of trouble: the panel ran dry (a glass miss), the main loop held up ("took a long time"), the wake word's ring
buffer reset. A sign climbs one step (a burst within two seconds is one sign); ten seconds of rest steps back down. A
wake word reset climbs straight to the step that squeezes the tiles. A finger on the glass steps the camera, sensing
and background down before any sign; a drag the tiles too; a second after release, all back. While someone hears the
screen's microphone (a plugin's `capturing(SOUND)`, 0.23: its video watched with its sound, a call) the live tiles
stay at a quarter whatever else: a conversation goes before the tiles on the sending side too (PLATFORM_PLAN 5.1). Each work reads its level
on its own task (`level_of`); plugins read it as `tessera::squeeze` (API 0.21). Home Assistant sees it as the
diagnostic sensor "Pressure". Detail: docs/PLATFORM_PLAN.md 4.10; test: `tests/test_pressure.cpp`.

### 8. The audio owner

`audio_owner.h`: one speaker, one microphone, several claimants. Every one of them claims a side (OUT, IN, BOTH) in a
role, like an audio session on a phone: DOORBELL > VOICE > CAMERA_SOUND > MEDIA. A higher role takes the side and hands
it back afterwards to whoever asked to have it back; a plugin's short sounds and announcements mix over whatever plays
and never claim. Detail: docs/PLATFORM_PLAN.md 3.4, docs/P4_AUDIO.md; test: `tests/test_audio_owner.cpp`.

### 9. The top bar, the doorbell, the modules

`header_bar.h` draws what the add-on decides to show and counts its own clocks; an item may carry an end (`until`), so
a missed doorbell ring leaves the bar after the minutes its automation chose (`keep_minutes`, default 30 for new
automations, 0 or absent means until someone opens it). `module_doorbell` opens a camera live with a chime on a ring
and prepares the keys; the talk-back is prepared in the audio owner and not built. Detail: docs/DOORBELL.md; tests:
`tests/test_header_bar.cpp`, `screen_manager/tests/test_doorbell.py`.

### 10. Plugins

`plugin_api.h` is what a component of someone else may use: tile types, cards, top bar items, settings rows, questions
to the app, audio through the owner, `squeeze` (0.21) and the screen's own camera's frames for a tile of its own
(0.22). The core keeps a list and names no plugin; a tile type the screen lacks draws as a plain card, never an error.
Tessera's own plugins move with the API in the same release, no compatibility layer, and the API keeps one form for
each thing (0.24 took away `on_touch`, the key and value form of `action`, `saver:picture` and `memory: {bytes}`);
its history is the plugins repository's, not the header's. Detail: docs/PLUGINS.md;
the plugins repository's docs/FIRMWARE_API.md.

### 11. Watchers and records

What the screen keeps about itself, so a crash or a stall is read instead of guessed: `loop_record.h` (the main loop's
stack at a task watchdog, kept across the reset), `ppa_trace.h` (the last PPA calls), `heap_watch` (the lowest internal
RAM with its time), `screen_diagnostics.h` (what the troubleshooting report and the API log carry: pictures a second,
glass waits, misses, pressure), and Debug mode (quiet by default; a report switches it on). Detail: docs/REPORTS.md,
docs/TROUBLESHOOTING.md.

## The hard rules, and the measurement behind each

- **Nothing in the shared code reads a board, a chip or a pin.** The engine table, the modules table and `hw::caps` are
  the three places a difference between boards is written. A board file holds hardware and sizes only (AGENTS.md).
- **One user of the 2D-DMA at a time, under the glass lock.** Two at once from different tasks hangs the P4
  (espressif/esp-idf #18999, #19108, #19096). Copies cannot leave the hold.
- **PSRAM shares its bus with the panel.** On a P4 the DSI panel scans PSRAM; on an S3 the RGB panel reads it through
  bounce buffers. Hot buffers in PSRAM cost blue frames on a P4 (measured 2026-10-25) and a sideways frame on an S3.
  Before any buffer moves, measure `glass::misses` on DSI; on RGB, look. Wi-Fi and lwIP stay in internal RAM on an S3.
- **Nothing of ours runs above the voice (priority 3) except the glass, audio and Wi-Fi.** Streams at 2, the writers'
  priority 5 only while holding the glass. Streams above the wake word cost a reTerminal D1001 644 resets an hour
  (2026-10-28); at 2, none.
- **A live tile shows at most 6 pictures a second, paced by time.** 10 a second on four tiles cost 51 wake word resets
  in three minutes (2026-10-28). Skipping decodes saves nothing on a pull link.
- **One PPA copy per tile picture.** Two copies (38 ms a picture) made four tiles wait on each other under the lock
  and froze a slider's frame blue; one copy took the picture's age on a D1001 from 1 s to 6 ms (2026-10-28).
- **The app delivers at card size and turned as the glass is.** The engine never scales or turns for a tile; a turned
  copy per picture is the class that stalled a Tab5 (docs/PLATFORM_PLAN.md 4.7).
- **Internal RAM never below 32 KB at rest.** The S3 engine's memory comes from PSRAM; an S3 runs one live tile
  because each tile's socket buffers cost about 11 KB of internal RAM (two tiles: 16 KB left, three: 3 KB; 2026-10-28).
  `live_view::open` holds it for every stream: no more at once than the engine's `streams` (an S3's 1, a full view and
  a stream still ending counted), and none that would leave less than 32 KB free (a tester's S3 aborted with a view
  beside a tile, 2026-10-30).
- **Limits are read, not inferred, in three places that agree.** The engine's `live_tiles`, the add-on's ceiling of
  eight streams over all screens (visible in the editor and the log), and the hello that carries both.
- **Measure, keep what works.** A change that measures nothing is not taken (the L2 cache size, esp_hosted's internal
  build, PERF optimisation was taken because it measured). Tests on a device run an hour at most.

## Where the add-on meets these layers

| firmware | add-on (`screen_manager/app/`) |
|---|---|
| the hello, `hw::caps`, `picture_turn` | `core.py`, `picture_service.py` |
| the question (`picture_question.h`) | `picture_service.py`, `picture_links.py`, `live_pictures.py` (turning, sizes, the fallback to upright) |
| the streams (`live_view.cpp`) | `live_stream.py` (the pull link, `X-Made`, `X-Turn`, the ceiling, `LiveFeed`), `camera_source.py` (WebRTC, snapshots) |
| the doorbell (`module_doorbell`, `header_bar`) | `doorbell.py` (the wizard, `keep_minutes`) |
| plugins (`plugin_api.h`) | `plugins.py`, `plugin_manifest.py` |

Detail: docs/PICTURE_ARCHITECTURE.md section 4; the add-on's tests in `screen_manager/tests/` run before every push.

## What is built and what is still a plan

docs/PLATFORM_PLAN.md is the plan with its measurements. Its sections 3.1 to 3.4 (the P4 core file, the chip facts
behind the seam, the capability record, the audio owner), 4.1 (the cap three places share), 4.4a (the PSRAM bus rule),
4.7 (what the PPA still turns), 4.10 (the governor), 4.11 (the own camera's tile) and 4.12 (pictures turned by the app)
are built and described above; 3.2 has its second engine, the S3. Open: a second S3 tile (Wi-Fi buffers in PSRAM,
measured against the panel bus), the D1001's video over Wi-Fi (4.8), the sensor's binned mode (4.6), the talk-back (5).
