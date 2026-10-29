# The core functions: a plan

What Tessera builds next on the ESP32-P4 boards, and in what order: a hardware layer the shared code talks to instead
of the chip, memory and live cameras with limits a user can read, and the ground for a doorbell you can talk back to.
Written 2026-10-25 after the P4 memory work (CHANGELOG, heap_watch, psram_task) and a review of the seams the code has
today; docs/PICTURE_ARCHITECTURE.md says how the picture path is built, this page says what changes and why. The rules
that already hold stay (AGENTS.md: behaviour lives once, a board file holds hardware and sizes only, no capability rules
by hand).

> **Where this plan stands (2026-10-28).** This page is a plan with its measurements, written as the work went, so an
> early section may describe a state that is gone. docs/ARCHITECTURE.md is the map of what is built now; read that for
> the current shape and this page for why and what was measured. Built: 3.1 to 3.4, 3.2 with the S3 as its second
> engine, 4.1, 4.4a, 4.7, 4.10, 4.11, 4.12. Open: 4.6, 4.8, 4.9, a second live tile on an S3, and section 5.

## 1. Where we stand

A few thousand screens run Tessera, a few hundred of them on a P4. The S3 boards keep their refreshed stills and stay
out of this page. Everything with video is the P4's: live camera tiles, the camera full screen with its sound, the
screen's own camera as video for Home Assistant, and a doorbell that rings on the glass. Users now ask for five live
tiles on one screen, and the doorbell should one day hear them back and open the door.

What the review found (2026-10-25, branch dev):

- **The picture path has its seam.** `picture_engine.h` (decode, blit, client) and `glass.h` (frame buffer, rooms,
  one-writer lock) are the only places the shared code meets the chip; `p4_build.py` picks the engine and the linker
  wraps, and S3 boards and the host get inline stubs for free. No `#if` on a chip name exists in `smart_display`.
- **Three chip facts leak out of the engine:** `glass::PPA_BURST_BYTES`, the PPA's sixteenths in
  `live_view::scaled()`, and the picture sizes of `live_view.h` (`MAX_PICTURE`, `TILE_PICTURE`) that come from P4
  measurements.
- **The Tab5 is a second P4.** `hardware/m5stack-tab5.yaml` does not include `esp32p4-c6.yaml`: it carries its own
  esp32 and hosted block and misses what the other P4 boards got this week (`CONFIG_ESP_HOSTED_MEMPOOL_PREFER_SPIRAM`,
  the 20 s watchdog). The Tab5 tester's restarts every few minutes are consistent with that.
- **Audio has no owner.** The camera's sound and Home Assistant's media both `start()`, `stop()` and
  `set_audio_stream_info()` on `ts_media_speaker` with nothing between them; the voice plugin, the tap sound and the
  doorbell chime share the announcement input through the mixer alone; the microphone is shared by listener count.
  Nothing says who may speak or listen when a doorbell is open.
- **Plugins cannot ask what a board can.** The API (0.18) exposes `ui::pictures()` and nothing else; `ui::live()`
  degrades to stills without a word. A board's features reach plugins only as build-time ids
  (`plugin_manifest.py`).
- **Limits are scattered.** The firmware allows seven streams a screen (`live_view::MAX_STREAMS`), the add-on eight of
  all screens together (`live_stream.MAX_STREAMS`), the editor nothing; none of the three knows the others, and a
  refused stream leaves a still without saying why.
- **The network is the ceiling, not the memory.** Espressif measures 30 Mbit/s TCP into a P4 over the C6's SDIO link
  in the open air (esp-hosted-mcu, docs/design/performance.md); a 1280 x 720 picture is about 80 KB at the add-on's
  quality, a full view at 13 pictures a second about 1 MB/s. Five tiles fit the bandwidth, but esp_hosted's own SDIO
  reader drops blocks under sustained inbound load (espressif/esp-hosted-mcu #197, open), which the 20 s watchdog now
  survives as a failed call. The add-on already paces every stream by back-pressure (the newest frame once the socket
  drained), so a slow screen gets fewer pictures, never older ones.
- **Memory is a policy, not a leak.** ESPHome builds the P4 with `CONFIG_SPIRAM_USE_CAPS_ALLOC`, so every plain
  allocation takes internal RAM and each consumer must be moved to PSRAM by hand (`roomy.h`, `psram_task.h`, the
  esp_hosted and lwIP options). Espressif's own P4 default is `SPIRAM_USE_MALLOC` with an internal threshold. That is
  the structural fix and an ESPHome-wide one.

## 2. The order

1. **The hardware layer** (section 3): one P4 core file, the chip facts back in the engine, a capability record the
   firmware, the add-on, the editor and the plugins all read, and an audio owner. Future-proof work, mostly moves.
2. **Memory and cameras with limits** (section 4): a cap on live tiles that three places share, a memory governor
   that stops a stream before the heap runs out, the soak that measures the SDIO link, and then the allocation policy.
3. **The doorbell's talk-back** (section 5): prepared, not built. The audio owner from step 1 and an uplink the add-on
   bridges are the whole preparation.

Each step lands on dev in pieces its testers can run, with a CHANGELOG line where a user would notice.

## 3. The hardware layer

### 3.1 One P4 core file

`packages/hardware/esp32p4-core.yaml` holds what every P4 shares whatever its radio wiring and panel: the chip, its
frequency and revision switch, PSRAM mode and speed, `execute_from_psram`, the watchdog, and the whole `sdkconfig_options`
block (esp_hosted mempool, PSRAM task stacks, `MEMPOOL_PREFER_SPIRAM`, thread-local pointers). `esp32p4-c6.yaml` and
`m5stack-tab5.yaml` include it and keep only their pins, SDIO frequency and LDO. A Python test asserts that every board
whose variant is esp32p4 reaches the core file, so the next P4 cannot miss it.

Done when: the Tab5 builds from the core file with no sdkconfig of its own, and `tests/test_live_view.py` (or a new
`test_boards.py`) fails on a P4 board file without it.

### 3.2 The chip facts back behind the seam

- `picture_engine::limits()` returns what today sits in `live_view.h` and `glass.h`: the burst bytes, the largest
  picture and tile picture, the scale steps (sixteenths), the largest side the decoder takes. The software engine
  returns zeros, and `live_view` and `glass` read the record instead of constants.
- `glass.h` loses `PPA_BURST_BYTES`; `glass_dsi.cpp` asks the engine.
- `PICTURE_ARCHITECTURE.md` section 2.4 (the table of every hardware fact and where it is read) is brought up to date
  (the panel wrap lives in `glass_dsi.cpp` now) and gains the rule: a chip fact is read from `picture_engine::limits()`
  or a wrap, never from a header the shared code includes.

Done when: `grep -rn "PPA\|sixteenth\|MIPI\|JPEG" components/smart_display/*.h` outside `picture_engine*.h`,
`ppa_guard.h`, `picture_jpeg.h` and `glass_dsi.cpp` finds comments only, and a test keeps it so (the way
`test_live_view.py` keeps `DIAGNOSTIC_WRAPS` to what `abort_record.cpp` defines).

Built in part (2026-10-28), with the S3 as the second engine that proves the seam:

- `USE_LIVE_VIEW` meant three things at once. Each is its own define now, from one table by chip (`engine_build.py`):
  the engine (`PICTURE_ENGINE_P4`, `PICTURE_ENGINE_S3`), the glass (`GLASS_DSI`, `GLASS_RGB`) and the streams
  (`USE_LIVE_VIEW`). A P4 builds the same code as before; an S3 has all three too.
- How many live tiles a screen streams at once is the engine's (`limits().live_tiles`), where `hw.h` had a constant.
- The S3 with PSRAM decodes JPEG stills in software (`picture_engine_s3.cpp`, esp_new_jpeg 1.0.2): its questions name
  JPEG first, and the app sends photographs as JPEG. Its decoder writes a row of MCUs at a time with a pause between, as
  the RGB panel reads its picture from the same PSRAM; whether the panel shifts a frame meanwhile only an eye can tell,
  since an RGB panel's driver counts no underrun (`glass::misses` is the DSI's alone). The decoder's own memory comes
  from PSRAM (a wrap of its allocator): asked inside the chip, as the library does, it took the internal RAM down to
  33 KB at a camera's full-screen stills. Measured on a Guition 4848S040, the same dev with BMP and with JPEG
  (2026-10-28, a camera tile's stills on its page, then the camera full screen):

  | A still | BMP | JPEG |
  |---|---|---|
  | camera tile, 448 x 118: bytes | 54 KB | 10 KB |
  | from the ask to the picture ready | 107 to 325 ms | 109 to 361 ms, 20 to 29 of it decoding |
  | full view, 480 x 270: bytes | 389 KB | 25 KB |
  | from the ask to the picture ready | 426 to 559 ms | 120 to 439 ms, 45 to 59 of it decoding |
  | internal RAM at its lowest | 42 KB | 43 KB (33 KB with the decoder's memory inside the chip) |

- Live pictures on an S3's RGB panel (2026-10-28): the glass is split into what every panel shares (`glass_core.cpp`:
  the lock, LVGL's hooks, the rooms) and a file per panel kind (`glass_dsi.cpp`, `glass_rgb.cpp`); the S3 engine
  decodes a stream's picture off the glass and copies it with the CPU (`blit`, as it is and not turned), and the
  engine's limits say what differs (`decode_on_glass`, `view_pps`, `live_tiles`, `tile_budget_pps`, `stream_core`;
  4.1, docs/CAMERA.md "Live on an ESP32-S3"). The seam the streams use is the one they had, `Block` and `blit`: the
  app sends a tile's pictures at the card's size and turned as the glass is, so no engine scales or turns for a tile,
  and no further engine API came of this first caller.
- Still to do: the grep and its test above.

### 3.3 One capability record

Today the hello sends "live" and "doorbell" when `live_view::available()` is true, `boards.json` says `camera` per
board, and plugins guess. One record replaces the three:

```
struct Caps {           // hw.h, read at boot, constant after
  bool live_video;      // picture_engine::JPEG && glass::direct()
  bool speaker, microphone, echo_cancel, camera;
  uint8_t live_tiles;   // the most live tiles this board runs at once (section 4.1)
  uint32_t psram_bytes, internal_bytes;
};
const Caps &caps();
```

Built (branch platform-core, 2026-10-25) as two halves. The build's half is `hw_build.py`: it reads the configuration
ESPHome validated and defines `HW_SPEAKER`, `HW_MICROPHONE`, `HW_ECHO_CANCEL` and `HW_CAMERA` when a component of that
kind is in it, wherever it came from (a part file, a feature, an override); it reads no id, no board name, no chip. The
boot's half is what only the running screen knows: `live_view::available()` and the two heaps. `hw::resolve()` puts
them together, pure and tested on a PC (`tests/test_hw.cpp`); `hw::caps()` resolves once on its first call.

- The hello carries the record as `caps` beside the features; "live" and "doorbell" stay for an app that reads only
  those. The add-on reads it in `page_delivery.caps_of`, with `live` from the features for an older firmware and
  `None` for a count it did not give, so an older screen is taken for what it says, never for more.
- The plugin API (0.19) gets `hw::caps()`, read-only, through `plugin_api.h`. `ui::live()` keeps degrading to stills,
  but a plugin can now say why on its own card.
- Still to do: the editor reads `caps.live_tiles` for its text and badge (section 4.1), and `boards.json` stays for
  screens that have not said hello yet.

Done when: the add-on's `live_pace`, the doorbell's feature check and the editor's live-tile count all read the hello,
and `FIRMWARE_API.md` documents `hw::caps()` with the rule that a plugin never infers hardware from a board name.

### 3.4 An audio owner

Built (branch platform-core, 2026-10-25): `audio_owner.h`, pure and host-tested (`tests/test_audio_owner.cpp`), one
owner of the loudspeaker (OUT) and the microphone (IN), the way iOS owns a device's audio session: whoever wants a
side claims it in a role, hears `lost` when a higher role takes it, and `regained` when that role gives it back, if it
asked to wait.

```
enum class Role { MEDIA, CAMERA_SOUND, VOICE, DOORBELL };   // lowest first
bool claim(Side side /* OUT, IN, BOTH */, const Claim &c);  // role, id, lost, regained
void release(Side, Role, id);
Role holder(Side); bool held(Side); bool would_grant(Side, Role);
```

The ranking as Max set it (2026-10-25), highest first: a doorbell's ring (and later its talk) takes everything and
nothing takes it; the voice assistant takes the speaker from a camera's sound and gives it back after the session; a
camera's sound takes the speaker from music, which does not start again by itself; short sounds (the tap, a plugin's
click) and Home Assistant's announcements never claim, they mix on the announcement input over whatever plays. The
same role replaces its holder (a second camera's full view takes over from the first).

- The core's own claims: `live_view.cpp` claims the speaker for a full view with sound in the role its opener gives
  (`live_view::open`'s `role`): CAMERA_SOUND for a camera someone opened (`lost` holds the sound back as a mute does,
  `regained` lets it through again), DOORBELL for the view a ring opened (`runtime_tiles` `live_begin` reads
  `doorbell::shown()`), so the ring's own camera sound plays and nothing takes the speaker from it; the ring itself
  claims nothing, its chime mixes on the announcement input. `features/audio-player.yaml` claims MEDIA through the
  media player's `on_play` (its `lost` pauses it; music that starts while a higher role holds the speaker is paused at
  once) and releases on `on_pause` and `on_idle`.
- The plugin API (0.19) offers it as `tessera::audio`. The voice plugin claims VOICE IN while its wake word listens
  (`lost` stops the wake word, `regained` starts it) and BOTH for a session, on tessera-plugins dev.
- The mixer and the half-duplex interval stay as they are: the owner decides who may start; the mixer mixes the
  announcement input over the media input as before.
- Still to do: the IN side for the doorbell's talk (section 5). Proven on the D1001 (2026-10-25): music under a ring
  (the ring takes the speaker, the music stays paused after it), music started during a ring (refused, paused within a
  second), a ring while the wake word listens (the wake word rests during the ring, and "Okay Nabu" opened a session
  right after it, 12:46).
  Found then, and kept: a camera's stream stops under every popup (LVGL draws over its room), so a voice session's
  popup ends the camera's sound with its stream, and the view asks again and claims the speaker anew after it. Whether a
  stream may go on under a popup is a question of its own, for later.
- A ring's view claims the speaker and the microphone (live_view, role DOORBELL, both sides), so the wake word rests
  during a ring and listens again after it ("doorbell took the microphone from voice", "doorbell gave the microphone
  back: voice has it again"; the voice plugin's claims, voice_assist 0.4.0). Open: the claim lives with the ring's
  stream, so a stream that breaks and opens again claims anew (the same role replaces itself, harmless), and one that
  ends while the ring's view stays (stills after three breaks) lets the wake word back under an open ring. The clean
  way is module_doorbell holding the claim for as long as the ring is up, which waits for the talk's design (section 5).

### 3.5 Allocation as a seam

`roomy.h` and `psram_task.h` are the memory layer of the shared code. The rule, written in `PICTURE_ARCHITECTURE.md`
section 8 and kept by a grep test: feature code (`live_view`, `picture_fetch`, modules, plugin host) calls `roomy` and
`psram_task`, never `heap_caps_*` or `xTaskCreate*` directly; only the two headers and the engines may. The test lists
the files allowed to say `heap_caps` so a new one fails the check until it is reviewed.

### 3.6 The screen's own camera

Screen camera's video encoder registers its own PPA client and hard-codes the burst length. It should use
`picture_engine::client()` and a `convert()` operation the engine gains for YUV input, so the one-2D-DMA-user rule and
the burst fix hold for it too. Low urgency: it works and the wraps already catch its calls. Noted so the plugin API
grows the right way.

### 3.7 Declare below, resolve above

More boards come every few months, so the layering is the product. The rule, from the bottom up, each layer knowing
only the one under it:

1. **The board file declares parts and pins.** `packages/boards/<board>.yaml` says "the microphone is an ES7210 on
   these I2S pins, the speaker an ES8311 on these, the camera an SC202CS on this I2C bus, the panel this size at this
   DPI" and nothing else: substitutions and includes, no logic, no ids of its own (AGENTS.md: a board file holds
   hardware and sizes only). Today the audio transports are chosen by hand (`TAB5_AUDIO_TRANSPORT`,
   `P4_AUDIO_TRANSPORT`, `es7210-aec.yaml`, `guition-p4-audio.yaml`); the board should name the part and the part file
   should know its transport.
2. **A part file resolves a part to ESPHome components.** `packages/hardware/parts/<part>.yaml`, one per codec, sensor
   or panel (`es7210.yaml`, `es8311.yaml`, `sc202cs.yaml`, …), turns the declaration into the components and binds them
   to the fixed ids the layer above expects: `ts_microphone`, `ts_speaker_out`, `ts_camera`, and a few facts as
   substitutions (`AUDIO_MIC_AEC: true`, `AUDIO_SAMPLE_RATE`). A part that brings echo cancellation declares it here.
3. **The feature layer builds on the ids alone.** `features/audio.yaml`, `audio-player.yaml`, `camera.yaml` never see a
   pin or a chip: they wire `ts_microphone` into the mixer, the resampler, the owner (3.4) and the plugins' ids. A board
   without a part leaves an id unbound, and the feature file is skipped by the board's includes, as `features/audio.yaml`
   already is.
4. **The firmware resolves what exists at boot** into `hw::caps()` (3.3) and the top layer says "the microphone of this
   board": `audio_owner::claim(Role::VOICE, Side::IN)`, `picture_engine::decode`, `glass::reserve`. No module and no
   plugin knows a chip name, a pin or a transport.

What this needs beyond 3.1 to 3.4: a `parts/` directory with the codecs and sensors the boards use today (five audio
parts, three camera sensors, the panel drivers), each board file rewritten to declarations only, and a Python test
that reads every board file and fails on anything but substitutions and includes. That test is a ratchet: it lists,
per top-level key a board file may still hold, the boards that hold it (`display: [tab5, wavesharep4, ...]`), fails on a
key or a board that is not listed, prints what is left when it passes, and a key leaves the list once its boards are
empty. Audio and the camera become parts first, with the Tab5 and the Waveshare set as the proof that a board builds to
the same sdkconfig and components from declarations; the panels and touch come last, because their files carry each
board's LVGL settings today and move only once those settings have a part of their own. `PROFILES.md` describes the
layering; it gains the part layer and the rule "declare below, resolve above". `ADDING_A_BOARD.md` then says: name the
parts, give the pins, done.

## 4. Memory and cameras with limits

### 4.1 A cap on live tiles that three places share

Four live tiles a screen, plus the full view (which halts the tiles anyway), on every P4 board; a fifth live tile on a
page shows the camera's still with a small "live paused" badge and a line in its settings ("This screen plays 4 cameras
live at once; the others show a picture every 15 seconds. With two cameras, each one runs more smoothly than with
four."). The four are what is on the glass: a live tile streams only while its page is open, so it is four on the page
the screen shows, and the other pages cost nothing. Two tiles run at 12 to 14 pictures a second each, four at 4 to 5
(the D1001, 2026-10-25): one PPA lays out every picture. The number lives in one place, the firmware's
`hw::caps().live_tiles`, and reaches:

- the firmware's `live_tiles_round`, which starts the first four by tile order and leaves the rest at
  `DEFAULT_PACE`;
- the add-on, which reads it from the hello and refuses a fifth stream of that screen with the 503 it already has for
  the global eight, and sets the editor's text;
- the editor, which shows the count on the page and the badge on the fifth tile as it is placed.

Why four: the soak numbers (two tiles plus the video held 175 KB internal RAM free with no failed allocation) leave room
for two more; the SDIO link carries it; and a user who reads "4" trusts the screen more than one who finds out which
fifth tile silently stopped. `MAX_STREAMS` stays seven for a page of four tiles, the full view and plugin places; it is
a ceiling, not the cap.

**The engine's numbers (2026-10-28).** The cap and the pace are the picture engine's (`picture_engine::limits`): its
`live_tiles` and `tile_budget_pps`, the pictures a second all streaming tiles share (`picture_engine::tile_pps`: the
budget over the tiles, at least 2, at most `hw::LIVE_TILE_PPS`). A P4 has 4 and 24, so its four tiles keep 6 each as
before. An ESP32-S3 with an RGB panel has 1 and 8 (docs/CAMERA.md, "Live on an ESP32-S3"): its CPU decodes every
picture, and each live tile took about 11 KB of internal RAM for its connection's Wi-Fi and lwIP buffers, two tiles the
lowest down to 16 KB and three to 3 KB on a Guition 4848S040. A second S3 tile waits for those buffers in PSRAM
(`CONFIG_SPIRAM_TRY_ALLOCATE_WIFI_LWIP`), measured against the panel's bounce buffers and 32 KB at the lowest; its
budget of 8 would give two tiles 4 each. The engine also names the core a stream's task runs on (`stream_core`): 1 on
a P4, 0 on an S3, where it took LVGL's core from 39 to 23 % busy with one tile.

### 4.2 The source scales, not the screen

The add-on knows every room it serves. Two rules it gains, both in `live_pictures`/`live_stream`:

- A tile room smaller than a quarter of the panel gets its pictures at most 8 a second, the full view at the camera's
  pace. The screen already shows what it gets; the add-on simply makes fewer.
- A screen's streams together stay under a byte budget per second it states in its hello (the P4's: 1.5 MB/s, half the
  measured TCP ceiling). Over it, the add-on lowers tile pictures a second first, then their JPEG quality (QSCALE 5 to
  8), never the full view's.

Done when: five tiles on a D1001 stream within the budget and `heap_watch` logs no failed allocation over an hour.

Open, for the add-on: a camera's source that falls far behind. On 2026-10-25 at 14:23 camera.max fell up to 10 s
behind ("Live camera.max video: 1.09 s behind the camera on average, 9.88 s at most"); its two live tiles on the D1001
went quiet, and the add-on answered their next streams 503 while the source connected again ("first WebRTC frame
9.9 s"). The screen did as it should (stills at the tile's pace). Whether the add-on should cut a source that falls
that far behind and start it again, and why WebRTC took ten seconds to give its first frame, is to be seen.

### 4.3 A memory governor

`heap_watch` sees the internal low-water mark every 250 ms. Instead of logging alone, it offers one action: when the
lowest since boot falls under 48 KB, `live_tiles_round` stops the newest live tile and marks it paused with the badge;
under 32 KB it stops the next; the full view is never stopped. A tile stopped this way starts again after five minutes
with room. The thresholds are constants in `heap_watch.h` with the measurements beside them, and the CHANGELOG says a
screen now pauses a camera before it would restart.

### 4.4 The soak that measures the link

Before the release candidate goes out, on a D1001 with four live tiles, the screen's own video and the voice assistant
in use, 24 to 48 hours, counted per hour: esp_hosted drops ("task still writing Rx data to queue"), RPC timeouts,
watchdog and abort restarts, the task count and both heaps (heap_watch's five-minute line). Then the same with
`CONFIG_ESP_HOSTED_USE_MEMPOOL` back on beside `MEMPOOL_PREFER_SPIRAM`, so the pool sits in PSRAM and every packet
stops going through `heap_caps_aligned_alloc`. The configuration with the lower drop count is the release's. The three
failure paths of `psram_task` are forced once in a test build (a start without PSRAM room, a download that overflows
its stack, a stream that ends while the main loop is in a long lay-out), and the lifecycle gets a host test.

### 4.4a The PSRAM bus is shared with the panel

PSRAM is not free memory: it is one bus, and the panel reads its frame buffer out of it every refresh (glass.h, "The
panel's share of the memory bus"; `glass::misses()` counts the frames it ran dry). The camera's frames, the JPEG
decoder, the PPA, the H.264 encoder and lwIP's copies all ride the same bus, and when it is full the picture tears
before anything else fails (Max, 2026-10-25, from the encoder's strip in PSRAM). So "to PSRAM" is a choice per buffer,
not a default:

- A buffer that is read or written in a tight loop many times a second, or by a DMA that must not wait (the encoder's
  reference strip, a stream buffer's control block, a task's hot stack) stays inside the chip, as long as it is small.
- A buffer that is large and touched once per frame or less (pictures, frame copies, documents, strings, the streams'
  read buffers) goes to PSRAM.
- Every move to PSRAM is measured against `glass::misses()` under load (four live tiles and the video) as well as
  against internal RAM: a move that frees 90 KB and costs frames is not taken.

Measured on the reTerminal D1001 (2026-10-25, two live tiles and three RTSP viewers of the screen's own video, the
same scene twice): with the H.264 encoder's reference strip inside the chip the panel ran dry 0 times, a picture's
lay-out took 60 to 63 ms, the video ran at 12 to 13 pictures a second, and about 243 KB of internal RAM was free; with
the strip in PSRAM the panel ran dry 39 to 53 times a minute (blue frames over the live tiles), lay-out took 77 to
80 ms, and 344 KB was free. The strip stays inside the chip: 100 KB of internal RAM is the price of a panel without
blue frames. A smaller burst for the encoder's DMA with the strip in PSRAM (64 bytes, the rule every other 2D-DMA
client keeps; tried the same day) saves the panel (0 dry runs) and halves the video (encoding 105 to 130 ms a frame, 6
to 7 fps): the strip stays inside, and every wrap of the test is gone. A move that passes on a D1001 is measured on a
Guition 10.1 before it is anyone's default.

### 4.5 The allocation policy, after the release

A dev cycle of its own: build the P4 with `CONFIG_SPIRAM_USE_MALLOC`, `CONFIG_SPIRAM_MALLOC_ALWAYSINTERNAL` at 16 KB
and `CONFIG_SPIRAM_MALLOC_RESERVE_INTERNAL` at 64 KB, so strings, vectors, plugin documents and TLS land in PSRAM
without `roomy` asking. ESPHome hard-codes `SPIRAM_USE_CAPS_ALLOC` in its psram component, so this needs either an
upstream option or a sdkconfig override that the build verifies; the soak of 4.4 is the measure, LVGL's draw times the
risk. If it holds, `roomy` becomes a thin name for "large and read by the screen alone" rather than the only road to
PSRAM.

### 4.6 The whole field of view, binned in the sensor (later, after the sensing steps)

Max wants a screen's own camera to show all it sees, not its middle. Scaling a larger mode down on the P4 is not the
way: the PPA is one device for the video and the live tiles, and a forced pass of 1280 x 720 into 960 x 528 beside two
live tiles took 77 to 89 ms a frame, the video fell from 12-13 to 7-9 fps and the tiles from 12-14 to 6-9 pictures a
second (CAMERA.md, "What travels"; PICTURE_ARCHITECTURE.md 2.4). A sensor that bins 2 x 2 itself gives the whole field
in fewer bytes than today, so the bus, the ISP and the PPA get it for free. It is the one way that costs them nothing.

- The board file names the sensor and how it is mounted, nothing more.
- The sensor's driver (the part: the OV02C10 in the screen camera plugin, the SC202CS through esp_cam_sensor) gains a
  binned mode, the OV02C10's about 964 x 544 over the whole field. It is register work: the Linux driver has no such
  mode. Checked on the glass with a ruler for the field and a colour chart for the Bayer phase.
- The FrameHub picks the mode from what is wanted of the camera, as it picks the frame rate.
- `hw::caps()` names the modes a screen's camera has.
- One setting per screen, "Field of view: whole / sharp", whole by default once a binned mode exists; the editor shows
  the choice and nothing else.

The sender of TR-YVP7YV, who also runs a Guition 10.1 and asked for its whole field of view (via Max, 2026-10-25), is the first to try it on an OV02C10, before it is anyone's default.

**Step 0, the SC202CS, measured (2026-10-25, the home reTerminal D1001, a test build not committed).** We have no
register map of the SC202CS, only its kinship with SmartSens' SC200AI, whose binned 960 x 540 mode is in Rockchip's
driver; every SC202CS driver found (esp_cam_sensor 2.4.0, Seeed's own copy in its reTerminal-D1001 repository, Ingenic,
Sophgo, MediaTek) knows only 1600 x 1200 and crops of it, and none writes a skip or bin register. The test handed the sensor a format of its own through `VIDIOC_S_SENSOR_FMT` (`sc202cs_set_format` writes any table
it gets, and esp_video takes the size from it), so nothing of esp_cam_sensor was patched: the 1600 x 1200 RAW8 table,
an output size in 0x3208-0x320b, offsets 2 in 0x3211 and 0x3213, and our black level.

- Rows: 0x3215 = 0x31 halves them over the whole height, with the colours right (no cast); with 0x3220 = 0x01 as well
  the picture looked calmer, as if the rows were averaged rather than skipped.
- Columns: nothing found. 0x3214 = 0x31 (the column twin of 0x3215 on other sensors) changes nothing; the SC200AI's
  0x3220 = 0x17 with 0x5000 = 0x46, 0x5900 = 0xf1, 0x5901 = 0x04 gives comb edges and still the left 800 columns at
  full resolution. So the output was the left half of the field, squashed to half its height.
- What came for free: an output in whole macroblocks (800 x 592) is encoded without the PPA's cut (0.0 ms, against
  47.8 ms a frame for 800 x 600), at 12 fps, and the encoder holds 65 KB of internal RAM instead of 103 KB.

- The nearest relative with a binned mode is the SC2355 (chip id 0xeb2c, the same 1/5" 1600 x 1200 family):
  Rockchip's `drivers/media/i2c/sc2355.c` (rockchip-linux/kernel, develop-5.10) has
  `sc2355_1lane_10bit_360Mbps_800x600_30fps_regs`, 29 registers apart from its 1600 x 1200 table: 0x301f 0x0c, 0x303f
  0x82, the output size, offsets 2, 0x3215 0x31, 0x3220 0x01, 0x5000 0x46, 0x5900 0xf1, 0x5901 0x04, its PLL and MIPI
  timing (0x36eb, 0x36ed, 0x4819-0x4829), 0x3904 and the exposure. It is a monochrome sensor (Y10), so its column
  merging need not keep a Bayer pattern. On the SC202CS, with our own PLL and timing: with 0x301f 0x0c and 0x303f
  0x82 the sensor sends no frame at all (DQBUF timed out, recovery exhausted); without them, 0x3220 0x01 with the
  0x59xx block gives comb edges and the left 800 columns again. The colour SC200AI's binned mode changes 0x301f as
  well (0x01 to 0x4e), so 0x301f might have been the switch of the 0x59xx block: with 0x301f 0x4e and with 0x0c (no
  0x303f) the frames come at 12 fps and the picture is the same as without it. 0x301f is not that switch, and 0x303f
  0x82 alone stopped the frames.
- Five colour sensors with a binned mode in Rockchip's drivers (sc200ai, sc230ai, sc3336p, sc431hai, sc435hai) and the
  mono SC2355 use the same recipe (0x3211/0x3213 0x02, 0x3215 0x31, 0x3220 0x01 or 0x17, 0x5000 0x46, 0x5900 0xf1 or
  0x01, 0x5901 0x04, the output size) with a 0x301f of their own. A last test swept that block on the SC202CS while it
  streamed (the whole window written out, x 0 to 1607, y 0 to 1207; every 20 s one value, read back): 0x5901 over 04,
  05, 06, 07, 0c, 14, 24, 44, 84, 01, 02, 03, 08, 00; 0x5900 over 01, f5, f3, f0, 00; 0x5000 over 06, 56, 66, c6, 40,
  00. Every value read back as written, at 13 fps throughout: the block is there. 0x5000 bit 6 turns it on, 0x5901
  bit 2 brings the comb edges and a black strip on the left, 0x5900 0xf5 a pink cast (it works on the Bayer pattern).
  No value halves the columns: the picture stays the left 800 columns at full width.
- github.com/youkorr/esphome_esp-video names an SC202CS "800x600 with 2x2 binning" in its notes; its table is a centre
  crop (window 396..1203 x 296..903, no 0x3215, 0x3220 or 0x59xx), and its own header says the sensor has no binning.
  Nothing to build on.

For the OV02C10 (step 3, the Guition) OmniVision's datasheet is known (OV02C10 product specification v2.01, in
Guition's own repository; the numbers below are its tables). The sensor has no scaler, only a window, binning and
skipping (table 2-1: "sub2 ... bin2 or skip2", "1280x720 crop from full"); a horizontal size must be a multiple of 8
(section 2.3). 0x3814-0x3817 step the columns and lines (X_INC_ODD/EVEN, Y_INC_ODD/EVEN), 0x3820 (FORMAT1) bit 1
(hbin2_o) bins two columns and bit 0 (vbinf_o) two lines, bit 3 mirrors and bit 4 flips, and 0x4501 (HBIN_CTRL) bits
3:2 at 00 average the binned pixels (table 3-1). The ISP reports what it does in 0x5024 (ISP_TOP_36: bit 5 x_bin2,
bit 4 y_bin2) and can be told by hand in 0x5003 (ISP_TOP_3: man_bin_en, man_x_bin2, man_y_bin2). So youkorr's "sensor
scaling" cannot exist: a smaller output than the window is a crop.

The test build is out (Screen camera 0.6.0 on tessera-plugins dev, 2026-10-25): the setting "Camera field of view"
(Sharp, Full (binning), Full (skip); Sharp by default). Both Full modes are the 1920x1080 table's whole window with
increments of 3 and 1 and a 960 x 528 output (the middle of 968 x 544, in whole macroblocks for the encoder); Full
(binning) also sets hbin2_o and vbinf_o (0x3820 0xa3) with 0x4501's averaging, Full (skip) reads every other pair
only, so fine patterns may shimmer. The setting asks the sensor's driver for the mode (`tessera_camera_field_format`,
the OV02C10's only), the capture task stops, hands the sensor the format and starts again, and the video's encoder is
made anew at the new size. A camera without the modes, and a mode that gives no frame, go back to Sharp by themselves,
and the setting shows it. Ten seconds after a change the log says the mode, its size and its frames a second, and what
the sensor says it does (0x3820 and 0x5024's x_bin2 and y_bin2). What the tester sends: which of the two worked, the
field (a ruler, or a room he knows, against Sharp), the colours, those frames a second, and whether the stream held
over a few minutes.

Where it stands: the whole field on the SC202CS needs the columns halved in the sensor, and that register is not
known without SmartSens' datasheet. Halving them on the PPA instead (a full-width 1600 x 592) is the pass that cost
the video and the tiles half their pictures. The registers above are all the test wrote beyond esp_cam_sensor's
1600 x 1200 RAW8 table. The OV02C10 (the Guition) is the other road: its binning and skipping are in OmniVision's
datasheet (table 3-1, above).

**Done for the OV02C10 (Screen camera 0.6.5, 2026-10-27, measured on a Guition 10.1).** Full is the default: the
1288x728 table's window opened to the whole array (0..1935 x 8..1087), the columns taken by pairs and averaged (0x3814
0x03, 0x3815 0x01, 0x3820 0xa2, 0x4501 0x00), every line read: 960 x 1080 at 15 frames a second (VTS 2328). With the
lines binned in the sensor too, every window tried stopped after one frame with a MIPI frame boundary error (0.6.3 and
0.6.4), so the FrameHub halves the lines once on the PPA, 960 x 528 for every consumer; what that costs against Sharp
is in CAMERA.md, "What travels". The FrameHub picks the frame rate too: 5 a second while nobody watches, full speed at
once when someone does. Both go through the sensor driver's own calls (`camera_sensor.h` in Screen camera:
`set_fps`, `field_format`, `field_report`), so the board file still names nothing of its sensor. Open: `hw::caps()`
does not name the modes yet; esp_video's auto exposure keeps the longest exposure of the format the camera started
in (Sharp's, about 32 ms, where Full's frame would allow twice that); and the halving waits its turn on the PPA behind
the tiles and LVGL (up to 0.74 s measured).

### 4.7 Open on the P4 (2026-10-27)

- **LVGL's areas in blocks of 16 (`draw_rounding: 16`) are not in.** On a turned glass it leaves the PPA no thin strip
  to turn, and 40 held top bars on a reTerminal D1001 froze it no more, but the guard (`ppa_guard.h`, a last unit the
  size of the 2D-DMA's FIFO counts as a stall) did the same alone, and the watchdog on the PPA ring (`ppa_trace.h`)
  restarts a screen within four seconds should a copy still never come back. The rounding's own first boot on the
  D1001 met the heap assert below, about 50 s in; its cost was not measurable (the screen showed its camera tiles as
  stills on the second run); no gain over the guard is proven. It stays out until one is.
- **A heap assert when a picture task is deleted, once.** On that D1001 boot: `assert failed` in `tlsf_free` (TLSF's
  "block already marked as free") from `prvTaskDeleteWithCaps`, `psram_task::reap`, `picture_fetch::tick()`, on the main
  loop, right after live pictures had loaded. The free that failed is the task's stack, in PSRAM (the call before the
  return address 0x48270e5e is `heap_caps_free(puxStackBuffer)`); the TCB is inside the chip, ESP-IDF 5.5.5's
  `xTaskCreatePinnedToCoreWithCaps` takes it with `pvPortMalloc`. The picture tasks left at least 7.9 KB of their 10 KB
  of stack unused, and the canary is on, so it is no overflow of their own. Suspects: a write past the end of the PSRAM
  block in front of the stack (TLSF keeps a block's size, with its free bit, in the word right after the block before
  it), or the stack freed twice. In the crashes the app kept of that D1001 since 2026-10-25 it never came before, and a
  serial watch stays on it. To do after Screen camera 0.6.5: light heap poisoning (`CONFIG_HEAP_POISONING_LIGHT`) in a
  test build, which names the block whose end was overwritten when it is freed, then an hour's soak on the D1001 and the
  Guition 10.1. The same family once before: 2026-10-25, a stream buffer's control block in PSRAM (live_view.cpp).
- **The screen's own video, measured with Screen camera 0.6.5 on the Guition 10.1 (2026-10-27, two live tiles, ten
  minutes a row).** While nobody watches, the camera makes 5 frames a second, for sensing or for nothing; that costs
  what nothing costs (laying out a live picture 26 to 28 ms, the cores at 23 and 39 %), where sensing at full speed
  cost 11 to 12 ms more a picture and 4 to 6 % of each core. A new viewer's first frame came after 2.4 to 2.5 s from a
  camera at 5 a second and 2.4 s from one at full speed: the switch costs 0.15 s at most, the server already asks the
  encoder for a key frame at PLAY (`rtsp_server.cpp`), and the rest is the RTSP handshake and the viewer's own probing
  (ffmpeg). Known load: with one viewer core 0 runs at 75 %; the video's server task, pinned there (Opus and RTSP),
  took 36 % of a core and the live tiles' tasks 37 %. Whether it, or the encoder on the camera's task, does better on
  core 1 is open, not tried.

- **A screen's own camera as a live tile goes out and comes back (2026-10-27).** Max's reTerminal D1001 shows
  `camera.tablet_video`, its own camera, as a live tile on page 1. That picture leaves the screen as H.264 and Opus
  over RTSP, goes through go2rtc and WebRTC into the add-on, and comes back to the same screen as a live tile with
  sound: as long as that page is on the glass, somebody watches, the camera never rests at 5 frames a second, and the
  screen encodes its own picture only to decode it again (core 0 at 85 to 88 %, four live tiles at 4.6 pictures a
  second where the Guition 10.1 keeps 14.8 with two). The add-on's log shows it ("Live camera.tablet_video ... 0.05 s
  behind the camera ... over 757 frames" a minute); no other screen and no dashboard watches it, and Home Assistant
  does not preload it. To do, as its own item: the firmware recognises its own camera (the screen's `camera.<node>_video`
  or its device id) and hands that tile its frames from the frame hub, with no RTSP, Home Assistant or WebRTC in
  between; the editor says so on such a tile. Not "only while the tile is visible": the tile is visible.

- **A live tile's turned copy that the guard calls safe stopped a Tab5, and the bench does not repeat it (2026-10-27).**
  A Tab5 of a dev tester (TR-2M2KX9; firmware 0.57.0 of dev, with the guard's equality rule and the PPA watch) stood
  still 88 s after boot and restarted on the task watchdog: the trace's last call, a live tile's card of 618x307 turned
  270 into the frame buffer at 16,646 by `live_view`, never came back, while its twin, 618x308 to 335,646, came back
  some 1,500 times; the night before, on an older build, nine restarts in 70 minutes with the same main loop record.
  That copy is safe by both rules (its output's last unit 51 x 10, 8160 bits): it is the chance class of
  espressif/esp-idf #19096, which no geometry rule catches. The PPA watch did not fire there: the esp_timer task it ran
  in did not get to it in 16 s. It runs in a task of its own now (`ppa_trace.h`), and the task watchdog's record keeps
  that task's state and stack (`loop_record.h`), so the next such report says where it stood.
  - **The rig, measured.** The Tab5's copies, 618x307 and 618x308 turned 270 to 16,646 and 335,646 in turn, from a
    canvas in PSRAM, each with the glass held, beside two live tiles and the panel's scan, counting copies until one
    never comes back (counters a restart keeps); the cost is the copy alone, inside the glass's lock:

    | Board | Variant | Copies | Time | Hangs | A copy | Panel dry |
    |---|---|---|---|---|---|---|
    | Guition 10.1 (rev 3.2) | (a) whole into the frame buffer, as `live_view` copies | 89,603 + 12,578 | 28 + 4 min | 0 | 8.5 ms | 0 |
    | Guition 10.1 | (c) whole into a PSRAM scratch no panel reads, then the CPU's copy, written back 16 rows at a time | 15,231 | 10 min | 0 | 23.0 ms | 0 |
    | Guition 10.1 | (b) 16 columns at a time into 307 x 16 in internal RAM, then the CPU's copy and write-back | 28,739 | 20 min | 0 | 26.8 ms | 0 |
    | reTerminal D1001 (rev 1.3) | (a) | 13,640 | 30 min | 0 | 24.0 ms | 0 |
    | reTerminal D1001 | (b) | 12,009 | 31 min | 0 | 44.0 ms | 0 |

    The Tab5 stopped after about 1,550 of its turned copies, and the night before every 8 minutes on average; the rig
    made 9 (D1001) to 66 (Guition) times as many of (a) without one, on a rev 1.3 and a rev 3.2 chip, and 55,000 of
    (b) and (c). Not repeatable on the bench, so (b) and (c) prove nothing, and they cost 1.8 to 3.2 times (a): (a)
    stays. With a Tab5 on the bench the rig goes there first. The rig is a bench hook (scratchpad), not in dev.
  - **Forced stalls** (#19023's 368x66 turned 270, past the guard), from the main loop and from a task like a stream's:
    on the Guition 10.1 the first copy stalled, into the frame buffer and just as well into a PSRAM buffer of the
    panel's size that no panel reads (#19023's reporter saw no stall into PSRAM, without a panel running): it is the
    memory bus's, with the panel scanning PSRAM, not the frame buffer's alone, so a scratch in PSRAM is no way out for a
    bad block. On the D1001 the same block came back at least 31 times, 2 ms each, before one stalled: a bad block
    stalls by chance too, only sooner. The watch caught every one: 3.1 and 3.8 s in the esp_timer task, 3.4 s (D1001)
    and 3.75 s (Guition) in its own, its words ending "esp_timer blocked".
  - **Found on the way:** a build for the P4's revision 3 (the Guition 10.1 of rev 3.2, its v3 profile) runs macro
    blocks of 32 rows, the engine's register says so ("the engine's macro block: 32 rows"), and the guard took 16 on
    every build; it asks the engine now, as the driver does (`ppa_guard.h`).
  - **What the next Tab5 stall must give:** the abort's words (the copy's size, angle and place, the task, and how the
    esp_timer task stood), or at a task watchdog the esp_timer task's record (its state, `TIMER0:` and on), and the
    trace with the copy that never came back. The suspect for the silent esp_timer task is a callback of a part the
    bench boards do not run (Bluetooth through esp_hosted, for its bt_proxy and toothbrush plugins); the record will
    name it.

- **A flash on the live tiles that comes with the log, not with the picture (2026-10-27, the bench Guition 10.1).** With
  two live tiles and the clock on a black page, Max saw both tiles flash at once for about a frame, bluish or white, the
  rest of the glass not, several times a minute. Measured with bench builds (sensors in the scratchpad, not in dev): per
  picture 32 pixels read back out of the cache after the decoder, on the glass just before the next copy (what the panel
  showed meanwhile) and right after the copy, with the JPEG's length, into a ring dumped on request; the panel's
  underrun counter (`glass::misses`) on a line the second it moves; later the main loop's longest absence per second and
  every time `keep_out` had to cut the whole glass or LVGL drew a frame over the live pictures. Flashes were timed by
  Max saying "now", 2 to 3 s late.
  - **Two things, not one.** Both tiles show the same camera, an EZVIZ C6T (`camera.max`, and `camera.woonkamer_live`
    from its address), with a television on in that room: twice the decoded picture of both tiles jumped at once, blue
    up by 50 in one picture and back over 4 s, or down by 17, 150 ms apart between the tiles (the camera's white balance
    at a change of light). That is the picture itself, not the screen. Every other flash came with the decoder flat (no
    step of 5 in brightness or blue) and the glass unchanged between copies (0 of 32 pixels, every picture), and the
    underrun counter at 0 throughout.
  - **The series**, the stream report of `live_view` (two lines of about 170 characters every 10 s) the variable: the
    logger on as on dev, the report every 10 s: flashes on the report's moments, five times out of five; (A) the report
    every 7 s: flashes more often, on its moments; (B) the report's lines left out: in 13 minutes only the two camera
    jumps and one flash right after a dump of the bench's own (230 lines that held the main loop 1.2 s); (C) the report
    through `printf` to the UART alone, past the logger and the API: flashes on its moments; (D) the logger off the UART
    (`baud_rate: 0`), the report to the API alone: flashes on its moments; (E, F) a false report of the same two lines
    from an interval 5 s off the silent real one: not separable by a person's 2 to 3 s; (G) the logger at level NONE
    from boot (`initial_level`), nothing to UART or API: Max watched a quarter of an hour and saw not one flash. In G
    `keep_out` never cut the whole glass, LVGL never drew over the live pictures, and the main loop was away 40 ms or
    more only four times (102 to 190 ms).
  - **So** the flashes that leave the framebuffer as it was come with the firmware writing log lines, by the UART or by
    the API, and not with any picture the screen copies. How a log line turns into a frame on the panel is open: the
    next step films a build with the dev's logging and the same sensors at 240 frames a second, with marks the board
    times (a white square for half a second), and then looks between "a line written" and "a frame different": the UART
    driver's interrupt, the API's send through esp_hosted, and what the main loop does in that millisecond. Whether a
    screen without a cable on its UART flashes the same is not measured: the bench's UART went to the Mac in every
    build, silent in D and G.
  - **The add-on's side, measured (2026-10-28).** Since Debug mode (dev 3574f2db) a screen writes warnings and errors
    alone, and Max then saw a white flash now and then, on every tile of the living room's EZVIZ C6T at once. The app's
    frame watch (camera_source.FrameWatch, docs/CAMERA.md "Every frame looked at", dev 653f7201 and e421f3bc) looked at
    every decoded frame on Max's Home Assistant for 25 minutes with the tablet's layout on the bench Guition: camera.max
    9,186 frames and camera.woonkamer_live 4,872 frames per ten minutes with 0 corrupt, 0 missing, 0 flashes (a single
    bright frame, and later any brighter moment of up to a second), 0 packets lost, 0 NACKs, 0 PLIs, 0 JPEGs the screen
    would refuse, 0 stills; nothing dumped. Max called out two flashes (07:10 and 07:14) in the first build's time, when
    the watch saw single frames alone; the bench Guition wrote no warning or error from 07:15 to 07:34. So the app sends
    no broken and no too bright frame of the EZVIZ; what Max sees comes after it (the screen's decoding, its copy to the
    glass, the panel) or is a part of the picture the mean brightness does not show. The white flash stays open; next,
    the filmed build H on the screen's side. The watch stays on dev as a lasting instrument.
  - **Others see the same (online, 2026-10-28).** jtenniswood/espcontrol#2118 is this board and this stack: a Guition
    JC8012P4A1 rev 3.2 with its C6 over ESP-Hosted SDIO, ESPHome 2026.9, IDF 5.5.5, "the whole screen occasionally
    flashes light blue for about one frame", brought on by HTTP downloads of JPEGs into PSRAM and the firmware's
    activity in general (here: log lines to the API, which go out through SDIO), with every diagnostic clean at the
    flash: the underrun interrupt never fires, the DSI host's status is empty, the DW-GDMA reports no error, the
    framebuffer sampled without blue. Its reporter asks whether ESP-Hosted's SDIO receive into PSRAM can disturb the
    DPI scan-out without a flag. What helped there: CONFIG_CACHE_L2_CACHE_LINE_64B instead of 128B ("largest effect";
    our P4 builds already run L2 128 KB with 64-byte lines, which may be why it is rarer here), fewer large LVGL
    invalidations with transparency or shadow, and no PPA scaling (pictures at their exact size). What did not: the
    pixel clock at 50 or 60 MHz, the lane rate, a cache-safe DSI interrupt, the AXI-ICM QoS, DMA outstanding, PSRAM at
    100 MHz (worse), XIP off, CPU rotation, BLE off, SDIO at 20 MHz, the power supply. rokudev/lt-sdk#22: writing into
    the framebuffer while the GDMA reads it out gives an underrun; a higher GDMA CH_PRIOR did not help; the bridge has
    registers nobody sets (DSI_BRG_RAW_BUF_CREDIT_CTL, DMA_BLOCK_INTERVAL, DMA_REQ_INTERVAL). Espressif's FAQ for
    "underrun happens": a lower lane rate or pixel clock, RGB565, SPIRAM_XIP_FROM_PSRAM, CACHE_L2_CACHE_256KB,
    CACHE_L2_CACHE_LINE_128B, COMPILER_OPTIMIZATION_PERF; the bench builds run OPTIMIZATION_SIZE.
  - **Work nobody needed, taken off the bus (2026-10-28).** Screen camera 0.6.6 (tessera-plugins 014c427): the frame
    hub halved every frame of the OV02C10's Full field of view on the PPA, 5 a second at rest (about 11 MB/s of
    PSRAM), for a video encoder that threw it away while nobody watched; it halves now only while someone watches the
    video. Five minutes before and after on the bench Guition with four live tiles: 0.0 frames a second halved at rest
    and with sensing at full speed, the tiles' lay-out 36.3 ms a picture before and 32.1 after, internal RAM 243 and
    246 KB free, the panel dry 0 times, the cores' load unchanged (the PPA did that work, not a core). Turning the
    camera off in standby was weighed and left: sensing at 5 a second costs next to nothing after this, and a light
    level that stops at night is something a person notices.
  - **One variable a build, measured (2026-10-28)** (the bench Guition, the tablet's layout with four live tiles,
    Screen camera 0.6.6, Debug mode on, a quarter of an hour each; the reference five minutes): the reference 26.6 and
    63.2 % on the cores, tiles 9.8 pictures a second, lay-out 32.1 ms, internal RAM 245.8 KB free (243.4 lowest); A, the
    L2 cache at 256 KB: 23.7 and 65.2 %, 10.8, 32.1 ms, 112.2 KB (110.4), no gain for 133 KB, not taken; B, ESP-Hosted's
    buffers and tasks inside the chip: 25.9 and 65.1 %, 11.5, 34.2 ms, 213.1 KB (202.9), no gain for 32 to 41 KB, not
    taken; C, the compiler optimising for speed: 27.7 and 52.1 %, 11.1, 26.5 ms, 238.8 KB (235.5), for 889 KB more
    firmware, taken for every P4 board (esp32p4-core.yaml). The panel ran dry 0 times in each; whether the flash comes
    less often cannot be told without eyes.
  - **Then** (the plan before the measurement): the dev's logging on so the flash shows, a
    quarter of an hour each, glass::misses and the PPA's waits noted): A, CONFIG_CACHE_L2_CACHE_256KB (128 KB of
    internal SRAM more for the cache: heap_watch before and after, with four live tiles and the video); B, ESP-Hosted's
    mempool and tasks out of PSRAM (CONFIG_ESP_HOSTED_MEMPOOL_PREFER_SPIRAM and DFLT_TASK_FROM_SPIRAM off, internal RAM
    measured); C, COMPILER_OPTIMIZATION_PERF. Then the underrun rig for the D1001's blue frame (a PPA copy loop of
    1280 x 800 RGB565 until the glass turns blue: does glass::misses count it).
  - **Wake word under load (the D1001, 2026-10-28 07:45 to 07:50).** Each page change with four live tiles brought 4 to
    6 "micro_wake_word: Not enough free bytes in ring buffer, resetting" and once "ui_refresh took 63 ms": a measure for
    the voice assistant under a busy screen.

### 4.8 The D1001's own video loses packets over Wi-Fi (after the doorbell's keys)

Found by the frame watch (2026-10-28): camera.tablet_video, the reTerminal D1001's own camera through Screen camera's
RTSP and Home Assistant's WebRTC, lost 100 to 780 packets every ten seconds, with 17 to 83 frames of 60 to 120 never
coming (11,762 packets lost and 1,408 frames missing over the half hour's ten-second lines), and the app sent hundreds
of NACKs and up to 14 PLIs a ten seconds; Max saw that tile fall behind. The EZVIZ on the same network lost nothing. To
measure on the D1001: the H.264 encoder's bitrate against what its C6 link carries (the ESP-Hosted SDIO path and the
air), RTSP over UDP against TCP (go2rtc asks one of them), and the cores' load with four live tiles on the same screen.
What screen_video can do then: lower its bitrate or frame rate while the uplink loses packets (the RTCP receiver reports
say so), or offer RTSP over TCP, where a lost packet is sent again instead of a frame breaking.

### 4.9 A ring's live picture is refused once while the screen's live tiles still run (after the doorbell's keys)

Seen at every ring on the bench Guition with the tablet's layout (2026-10-28): the view's stream gets a 503 at its
first ask ("not a stream of pictures (answer 503)"), the screen asks again, and the picture comes about 1.9 s after the
view opened instead of under a second. The add-on's limit is MAX_STREAMS (live_stream.py, 8 streams of every screen
together, "Too many live cameras"): the Guition's four live tiles and Max's D1001 with its own live tiles fill it, and
the ring's view asks before the Guition has closed its tiles (live_view's stream 4 starts, then streams 0 to 3 end).
The screen's own cap (hw.h LIVE_TILES) does not refuse it: a full view is no tile. Done (2026-10-28), both ways: the
screen's camera_open halts its live tiles before the view asks (live_tiles_halt), and the add-on lets a full view of a
screen through MAX_STREAMS while that screen's own tiles still stream (live_stream.serve). Measured on the bench Guition
with the screen's half alone: no 503, the first picture 1.54 s after the view opened (1.3 s of it the app's answer with
the link, the stream's first picture 226 ms after it started), and the four tiles back by themselves after the ring.
Done (2026-10-28): the app makes each view screen's link as the event comes and sends it in the op doorbell (`l`,
Manager.doorbell_link), its room coming with the screen's first open (`?room=WxH`), and starts the camera's source at
once (LiveFeed.warm); the view opens it before its first round and asks for nothing. On the bench Guition: the link open
17 to 22 ms after the view opened (245 asking first), the first picture 340 to 440 ms after it with the camera running
for the tiles, 330 to 670 ms with it cold. The first ring after a restart of the screen or the app connected slowly
(1.2 s), which is the first connection, not the ring.

### 4.10 The governor: what a busy screen gives up first (v1, 2026-10-28)

`components/smart_display/pressure.h` (tests/test_pressure.cpp), run from runtime_tiles.h on the camera's tick (250 ms).
The work of a screen in one fixed order, from what never waits to what gives up first: the glass, the voice assistant,
a doorbell's ring, the live tiles, the screen's own camera (its video), its sensing (light level, motion) and the
background (pictures fetched ahead for pages out of sight). Each has a level: 0 runs as it is, 1 does half, 2 a
quarter; the glass, the voice and a ring are never squeezed. Since 2026-10-29 (plugin API 0.23, `heard`): while someone
hears the screen's microphone (its video watched with its sound, Screen camera 0.6.12; a call, 5.1) the live tiles stay
at a quarter whatever the steps say, so the conversation's uplink is not starved by them: on a reTerminal D1001 four
live tiles beside its own video stalled the uplink, the sound reached the viewing screen in bursts a second late (2.4 s
at most) and that screen cut more than half of it away.

- **One mechanism.** Every sign of trouble climbs one step of a table, from the bottom of the order up: step 1 the
  background, sensing and the camera to 1; step 2 the camera to 2 and the live tiles to 1; step 3 the live tiles to 2.
  A sign within 20 s of the last one climbs, a burst within 2 s is one sign, and every 10 s without one the screen
  steps back down one, the live tiles first. A sign of a work above the tiles takes them at once: the wake word's
  reset climbs straight to step 2 (pressure.h, FLOOR), as on the D1001 its resets came seconds to a minute apart and
  the slow climb stopped at step 1 every time.
- **The signs**, all measured: the panel ran dry (glass::misses), ESPHome's "<component> took a long time" (the main
  loop held up) and micro_wake_word's "Not enough free bytes in ring buffer ... Resetting" (its inference fell behind),
  the last two from ESPHome's log listeners (pressure_log: only a count, on any task), warnings that come with Debug
  mode off too.
- **Before any sign, the finger.** While one is on the glass, the camera, sensing and the background step down one;
  once it drags past a tap's reach (or holds a slider), the live tiles too; a second after it lets go, all back at once.
  A tile at half its pictures during a drag of half a second goes unseen.
- **The knobs.** A live tile pauses after a picture until two or four times its own pace at rest has gone by, and
  reads nothing from its socket meanwhile (live_view, pace; never a full view or a still), so the app, which makes
  the next picture once the last one left its host, sends fewer and the Wi-Fi rests too. The first build left
  pictures out before decoding them instead, and that saved nothing: the stream is pulled, so the tile only read the
  next picture sooner (the D1001: 6.5 pictures a second shown either way, 26 KB/s became 60). Paced, a tile showed 4.1
  a second at 17 to 19 KB/s against 5.6 at 27 at rest. The background fetches nothing ahead; a plugin asks
  `tessera::squeeze(Work)` (plugin API 0.21): Screen camera 0.6.7 encodes every other frame or one in four of its
  video (after its own pace, which already leaves out every other frame of a camera at 30 a second) and samples its
  sensing half or a quarter as often.
- **What it says.** The diagnostic sensor "Pressure" in Home Assistant ("normal", or for example "live tiles 1/2, own
  camera 1/4, sensing 1/2, background 1/2 (the wake word fell behind)") and one warning in the log at every change; a
  live tile's line says how many pictures it left out. And the tile itself (2026-10-29): while the governor squeezes the
  live tiles, each shows speedometer-slow in white on a round dark chip where its loader turns (runtime_tiles
  live_badge, Look::badge). LVGL draws the chip once as the stream opens, off the glass; the stream makes its overlay
  with the mark the first time the tiles are squeezed (240 to 350 ms on the D1001, once) and lays that one over its
  pictures while they are, the plain one at rest, composing as fast as before (26.5 to 30 ms a picture).
- **Measured before it** (the reTerminal D1001, 2026-10-28, slider drags in a light's card with page 1's four live
  tiles and the camera's video): 27 wake word resets in 7 moments, ui_refresh up to 71 ms, the panel dry once, the
  cores at 73 and 57 % (the H.264 encoder 34.5 % of core 0), the tiles' lay-out 132 ms a picture against 32 on the
  Guition; the same drags on a page without live tiles: none of that. A light's card covers the tiles, and a covered
  tile stops, so the rounds after it drag up and down over the four live tiles themselves (from one tile to the one
  below, so no tile takes it for a tap; far from the edges, so it is no edge swipe).
- **The finger and the signs, on the D1001.** Three minutes of drags: the governor steps down within 250 ms of the
  finger and back a second after it lets go; without the finger's rule (a bench switch) the wake word's resets alone
  climb it to live tiles at 1/2 and 1/4 and back. The panel ran dry 0 times in every round.

#### What keeps a live tile waiting (measured 2026-10-28)

The D1001's tiles waited 40 to 90 ms a picture for the glass, up to 320, where the Guition's waited almost none. The
glass's lock, counted every 10 s (glass.h, Held; live_view's "glass:" line), says who held it:

- **Not LVGL.** Its refreshes held the glass 7 to 50 ms a second at rest and 23 during drags (drawing 11, the PPA's
  turn of its flush 7, the panel's copy with its wait for the end of it 4), at most 157 ms once for a page's redraw.
- **Not the stills.** Pictures fetched ahead and a still's decode: 1 to 17 ms a second of the streams' waits.
- **The tiles themselves.** 1.6 to 2.6 s a second of waiting, summed over four tiles, was behind another tile. A tile's
  picture held the glass about 40 ms: decoding 4, the PPA's copy into the card's canvas 18, its copy onto the glass,
  turned, 18.5 (composing the card, 20 ms, runs outside it). Four tiles at 5.5 to 6.5 pictures a second fill it.

The lock is also the rule of one user of the 2D-DMA at a time (the JPEG decoder, the PPA and LVGL's copy to the panel;
two at once from different tasks hang, espressif/esp-idf #18999 and #19108), and the PPA is one engine, so the copies
cannot move out from under it. What helps is less work for it: a live tile's picture the app sent at the card's own
size is composed where it was decoded and copied once, onto the glass, with no canvas between. On the D1001 a tile then
showed 8 to 10 pictures a second where it showed 5.3 to 6.3, its wait for the glass 22 to 30 ms instead of 60 to 84
(the copy onto the glass 17 ms; composing, outside the lock, 31 to 35 ms of wall clock, with the tasks' CPU unchanged at
9 %). At that rate the wake word fell behind 51 times in three minutes, so a live tile keeps to six pictures a second
on every board (hw::LIVE_TILE_PPS), and a busy screen's tile to three or one and a half. With all of it (one copy, the
newest picture below, six a second), three minutes of drags over the four tiles: the D1001's tiles at rest 5.6 to 5.7
pictures a second, 35 to 69 ms on the way, waiting 0.5 to 2.9 ms for the glass, the cores at 59.9 and 44.8 % (the
lowest of the day), one moment of 12 wake word resets on which the tiles gave way at once; the Guition 10.1's 5.6 a
second, 13 to 62 ms on the way, the copy onto the glass 6 ms, the cores at 19.6 and 30.9 %, no reset; the panel ran dry
0 times on either.

#### Pictures a second old: the queue on the way (measured 2026-10-28)

The app makes a tile's next picture once the last one left its host, so a screen that reads slower than its camera sets
the pace; but what lies between them holds a dozen of a tile's few KB pictures: the app's socket buffer (64 KB, which
Linux doubles) and the screen's TCP window (64 KB, raised for downloads; lwIP has no smaller one for a single socket).
Every picture now says when it left (X-Made, the app's clock in ms), and the screen sets that beside its own: what lies
over the quickest picture seen is its wait on the way ("its pictures waited ... ms on their way" in a tile's line).

- **At rest** three of four tiles showed pictures 0.86 to 1.18 s old on average (up to 2.3 s), one 74 ms.
- **Paused for a busy screen** without more, 11 to 14 s old: the tile read nothing, and the buffers filled.
- **First fix, now replaced**: the tile read on to the newest picture there was (a second input buffer, a picture
  waiting while more bytes waited in its socket): 19 to 41 ms on the way, but at the camera's pace in bytes (40 to 140
  KB/s a tile). The app keeps a tile's socket buffer at 16 KB.
- **Then a tile asks for each picture** (live_stream.py pull, live_view.cpp ask_each): GET on its link's .jpg over a kept
  connection, the app answering with the newest frame's JPEG once it is newer than the last it sent there, or 204
  after 2 s; the tile asks when its pace says (six a second, or a busy screen's share), so nothing queues and the bytes
  are what it shows. A tile whose app answers 404 (an app before it) reads the stream, passing a picture a frame behind
  when a newer one is on its way (read_stream), as the full view does, which keeps the stream for its sound. Measured on the D1001 (the same three minutes of drags):
  at rest 5.0 to 5.7 pictures a second, 4 to 6 ms on the way (at most 67), 24 to 31 KB/s a tile (the heaviest camera
  57 against 132 to 142); during drags 2.7 to 2.9 a second at 12 to 13 KB/s (against 4.4 at 57 to 60), the cores at
  54.6 and 40.7 %, the panel dry 0 times.

#### Who runs above the voice (measured 2026-10-28)

The wake word's inference (ESPHome's micro_wake_word, priority 3, fixed there) fell behind 644 times an hour on the
reTerminal D1001 at rest with four live tiles, its own camera's video on one of them: the tiles' tasks ran at 5 on the
same core. The tasks of a P4 screen, as a bench action listed them (name, priority, core):

| Task | Priority | Core | Whose |
|---|---|---|---|
| ipc0, esp_timer, sys_evt | 24, 22, 20 | 0 | ESP-IDF |
| mic_task, rpc_tx, rpc_rx, sdio_* | 23 | any | the microphone, ESP-Hosted's Wi-Fi |
| speaker_task, tiT | 19, 18 | any | the speaker, lwIP |
| isp_task, ppa_watch | 11, 10 | 0 | the camera's ISP, the PPA's watch (ppa_guard.cpp) |
| live_view while it asks for or holds the glass | 5 | 1 | live_view.cpp take_glass (glass::WRITER_PRIORITY) |
| screen_video | 4 | 0 | Screen camera's video (its encoder, RTSP) |
| mww | 3 | 1 | the wake word's inference |
| esp_video_cap | 3 | 0 | the camera's frames |
| live_view | 2 | 1 | a live tile or view: reading, composing |
| loopTask, mdns, Tmr Svc | 1 | 1, 0, any | ESPHome's main loop with LVGL |

The rule: nothing of ours runs above the voice (3) but the glass (a stream only while it asks for or holds it), the
sound and the Wi-Fi. A task that someone adds above it, or a stream that holds the glass for long, takes the voice's
turn. With the streams at 2 (ba8256cb) the D1001 had 0 resets in ten minutes at rest and in three minutes of drags,
against 108; the video's encoder stays at 4, on core 0, where the wake word does not run.

### 4.11 The screen's own camera on a tile of its own (2026-10-28)

A live tile that shows the screen's own camera (the reTerminal D1001's tile of its own Video) went the long way: the
camera's frames into the H.264 encoder (a third of a core), over RTSP to Home Assistant, to the app, into JPEGs, and back
over the network to the same screen, to be decoded there. Now the screen draws it from the camera itself:

- **The tie.** A plugin with the screen's camera offers its frames (plugin API 0.22, `tessera::offer_own_frames`;
  Screen camera 0.6.8), the screen's hello says `own_camera`, and the app answers the live ask of a tile of the screen's
  own camera (the tessera_video camera on the screen's device, or on a device of its own with the screen's MAC, as Home
  Assistant may keep them apart) with `own:` instead of a link (picture_service, `Manager.own_camera_of`). An app
  before it gives the link, a firmware before it never says `own_camera`: the hello's flag and the answer are all that
  ties the two.
- **The draw.** `own:` opens a stream with no socket and no decoder (live_view.cpp, `own_stream`). While it is open
  the plugin hands each camera frame to `tessera::own_frame` on the camera's task; the tile takes one when its pace
  says (hw::LIVE_TILE_PPS, a busy screen's share) and the glass is free at once (`glass::try_hold`: the camera's task
  never waits), and the PPA copies the part it shows into the card's canvas, scaled, from the camera's YUV420 or RGB565.
  The tile's own task composes the card over it (corners, shade, name) and lays it onto the glass in one more copy, turned.
  A frame it cannot take goes by. Covered, on a page out of sight or in standby, the tile closes as any live tile does,
  and the plugin's hub takes no frames for it.
- **The encoder** runs only while someone watches the video in Home Assistant (or a ring), not for the tile.
- **The shape, for what comes next.** The stream is a stream of frames from a source, the drawing shared with every
  live tile; the screen's own camera is its first source. A call between two screens, foreseen and not built: Screen
  camera's RTSP session as it is (H.264 and Opus, in step) straight from one screen to the other, without the app; on
  the screen that receives, a new source for the shared drawing (an RTSP client, the H.264 through the P4's hardware
  decoder) and the Opus played through the mixer with echo cancelled (the D1001's hardware reference channel, the
  Guition's in software); ringing, answering and hanging up through the app. The picture of oneself is today's tile of
  the own camera.

### 4.12 Live pictures come turned for a turned glass (2026-10-28)

On a glass that LVGL turns (the M5Stack Tab5, the reTerminal D1001 and the Guition 10.1: panels made upright, shown on
their side) every live picture went onto the glass through a turned PPA copy, the class of copy that stopped the Tab5
three times in two days (4.7: 618x307 turned 270 to 16,646, twice; the third, before 9eef23bf, a copy into a card's
canvas). The turn now happens in the app, where it costs little, and the screen copies a live picture straight:

- **The tie.** A screen whose glass is turned says in its hello `picture_turn`, LVGL's turn as the hello leaves
  (hw.cpp). The app turns every live picture of that screen by it, a tile's, a plugin's place's and the full view's, the
  same for a picture at a time and for a stream (live_pictures.TURNS: Pillow's transpose for a camera's JPEG, FFmpeg's
  transpose filter in YUV for video), its size worked out upright as before and then turned, and says so on every
  picture, `X-Turn` (live_stream.py). A picture it cannot turn goes upright without `X-Turn`, counted in the camera's
  frame watch line ("pictures not turned for a turned glass"), and the screen turns it itself: a turned screen never
  goes without its picture for the app's turn. The screen reads `X-Turn` per picture (picture_fetch::parse_head), so an
  app before it, which turns nothing and says nothing, gets the turned copy as before, and a screen stood up at run time
  copies what is left between the picture's turn and the glass's (turn_between).
- **The overlay, once.** What a tile lays over each picture is made once at a stream's first picture for the way its
  pictures lie, with the CPU (live_view.h, Overlay): the shade as how deep it darkens each row, or each column of a card
  on its side, and the corners and the name as short segments of pixels, each with one colour and how much of the
  picture it hides, laid after the shade. Each picture then costs the shade's darkening as before and one blend a pixel
  of the corners and the name; within a step of RGB565 of the three blends it replaces (tests/test_live_view.cpp,
  composing). A first version kept a colour and a coverage for every covered pixel of the card in PSRAM and composed in
  33 to 42 ms where the old composing took 30 on the D1001: the shade is a table now. The loader over a still lies and
  turns in the same way. A full view's room is worked out on its picture upright, and the picture scaled straight onto it.
- **Measured** (2026-10-28, ten minutes at rest, four live tiles on each board, one of the D1001's its own camera): every
  tile of the app's pictures copied at 0 on both boards (the stream's ten-second line, "turned 0 on the way"), the own
  tile at 270. Per picture, composing 26.4 ms on the D1001 and 15.0 on the Guition (30.0 and 16.2 before), onto the glass
  16.9 and 6.3 (17.6 and 6.1 turned): the straight copy is no quicker, the point is the hang. 5.2 and 5.6 pictures a
  second, 6 and 11 ms on the way, the panel dry 0 times, internal RAM at its lowest 191 and 196 KB. The app's share of
  Home Assistant's processor went from 43.9 to 45.3 % turning the pictures of seven tiles. The D1001's video was watched
  all along by the Guition's tile of it (13 frames a second encoded, a third of a core), and its wake word fell behind 10
  times in the ten minutes and 11 in three minutes of dragging, against 0 and 33 in two rounds of the build before with
  the same load: what decides it is the encoder, not the turn.
- **What the PPA still turns per picture:** a tile of the screen's own camera (its frames come upright from the
  sensor; one turned copy each onto the glass) and LVGL's own flushes. Tried and left out (2026-10-29, the D1001, three
  minutes each): the frame turned on its way into the canvas, which converts and scales it anyway, so the copy onto the
  glass goes straight. Into the canvas 57.7 ms against 52 to 55, composing 30 against 24 to 30, onto the glass 18.0
  straight against 17.8 to 19.8 turned: no quicker, and still one turned copy a frame, the kind the hang is about,
  into PSRAM instead of the glass. The sensor cannot turn a quarter (only mirror and flip), and the video wants its
  frames upright, so a turn in the frame hub would serve the tile alone: the turned copy onto the glass stays.
- **What the Tab5 should show:** its two live tiles no longer turn on the chip. Whether the stall comes back is for its
  tester to say; the ring of a stall names the copy and its turn as before.

## 5. The doorbell's talk-back, prepared

Not built now: Home Assistant is expected to bring a two-way audio path of its own within months, and the community
VoIP stack (a SIP endpoint inside Home Assistant) already bridges door stations. What the firmware prepares does not
depend on which one wins:

- **The owner.** Section 3.4: a ring claims BOTH, the wake word steps back, the camera's sound keeps playing. That is
  the "always hear the other side" rule.
- **Push to talk, half duplex** (the plan as of 2026-10-28). The view has its Talk key already (module_doorbell.cpp),
  grey with "Coming soon" and no action. Built, it shows only when Home Assistant reports `two_way_audio` true for the
  ring's camera. While it is held, the ring claims the microphone through the audio owner (3.4), the doorbell's own
  sound goes silent on the screen (half duplex: no echo cancellation needed, no feedback through the doorbell), and the
  microphone's 16 kHz PCM goes up the link the view already has to the add-on (a POST of `audio/x-s16le;rate=16000` on
  `/camera/<token>/talk`). Released, the uplink closes and the doorbell's sound comes back.
- **The add-on bridges.** The screen never speaks to a doorbell. Home Assistant 2026.11 brings two-way audio for
  cameras as a Labs preview: `camera/capabilities` says whether a camera has it, and `camera/webrtc/re_offer` adds an
  audio track to the camera's WebRTC session, for Reolink over RTSP only at first. The add-on encodes the PCM as G.711
  (PCMA or PCMU, whichever the offer takes) into that track; ffmpeg, which the add-on already has, does the
  transcoding. Reolink first, because testers have one, built once it runs on a Home Assistant with a Reolink doorbell.
- **Known risks.** go2rtc #1860: a backchannel that stays open after the talk ends, so the next talk finds it taken; and
  a Reolink takes one talk connection at a time, so a second screen that holds Talk gets nothing until the first lets go.
- **Open the door** is built (2026-10-28, docs/DOORBELL.md): the event's `lock` or `door_action`, a Door key that opens
  after a second tap, and the app performs `lock.unlock` or the action, as it performs an alert's button.
- **One rule for sound that falls behind, at both ends** (2026-10-25). The add-on drops the oldest part when a screen's
  sound queue is full (`live_stream.SOUND_QUEUE`), and the screen leaves the oldest out when more than 400 ms waits for
  its speaker, down to 150 ms (live_view `SOUND_HIGH`, `SOUND_LOW`). A part that finds the screen's buffer full is left
  out whole, the safety net under it. A conversation at the door keeps the same rule.

Done when (later): a tester holds the key on a D1001 and is heard at a Reolink doorbell, with the doorbell's sound on
the glass before and after, silent while the key is held.

### 5.1 Calling: screen to screen, later SIP (direction only, 2026-10-29)

Not built, and nothing here is code yet. A call is the doorbell's talk-back between two screens: one screen's camera
and microphone to another screen's glass and speaker, both ways. It reuses what the ring has, so nothing new is needed
on the screen beyond a key and a view:

- **The audio owner** (3.4): a call claims the speaker and the microphone as a ring does, the wake word steps back, and
  a ring at the door takes over from a call (the door goes first).
- **The uplink** the talk-back prepares (section 5): the microphone's 16 kHz PCM up to the add-on. The picture goes up
  as the screen's own camera already does (4.11, the video server); the other screen gets both as it gets any camera.
- **The add-on as the bridge.** A screen never speaks to another screen. The add-on joins the two uplinks to the two
  screens' links, so a call works across rooms and networks the app reaches, and later bridges a call to a SIP or VoIP
  endpoint in Home Assistant the same way it bridges a doorbell.
- **Half duplex first**: one side speaks while the other listens, as the doorbell's push to talk. Full duplex only on a
  screen whose hardware reports echo cancellation (`echo_cancel` in its caps, 3.1); without it the speaker comes back in
  the microphone.
- **What gives way** (a governor rule for later, 4.10): a doorbell's view and a call fill the screen, so while one is
  open it ranks above the live tiles, on the receiving screen and on the sending one: a screen whose camera with its
  sound someone watches squeezes its own live tiles, so its video and its voice keep their share of the bus and the
  link. Seen on a reTerminal D1001 with four live tiles on its page (2026-10-29): the sound it sent another screen broke up
  (words twice, words lost), and better on a page without tiles.

Done when (later): two screens call each other half duplex through the add-on, a ring interrupts the call, and the
sender with four live tiles on its page keeps clean sound.

## 6. What stays out

- Replacing ESPHome. Its board files, build server, override YAML, OTA and Home Assistant integration are why boards
  are cheap to add; the layer above (sections 3 and 4) is ours and stays ours.
- Ethernet or another radio as a way around the SDIO link. Boards will not have it; the link's budget is a rule the
  add-on keeps.
- H.264 on the screen. The P4 encodes, it does not decode; the add-on's JPEGs stay the format.
- A fifth live tile "when there is room". The cap is the feature.

## 7. Evidence to keep

Every step lands with its numbers in the commit message, as the P4 memory work did: the board, the date, internal RAM
free and lowest, pictures a second, drops an hour. Docs hold the rule that resulted, not the log (AGENTS.md).
