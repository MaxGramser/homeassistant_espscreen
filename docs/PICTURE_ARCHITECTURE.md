# Pictures and cameras: the building blocks and their layers

docs/PICTURES.md says what a picture is and how it travels; docs/CAMERA.md says what a person sees of cameras. This
page is about the code under both: the building blocks as they stand, where they lean on each other in ways they
should not, and the layers they are being moved into, with what each layer may and may not know. It is a design first
and a recipe second: section 6 is the refactor that follows it, in steps that each leave the screens showing exactly
what they show today.

Three products share these blocks, and the same rules hold in each: the firmware (`components/smart_display/`), ESP
Screen Manager (`screen_manager/app/`) and the Screen camera plugin (the plugins repository, `plugins/screen_camera/`).
Nothing of a board's name belongs in any of them (AGENTS.md, "Behaviour lives once"); what a board brings is a fact of
its chip, its panel or its sensor, and the layers below are keyed on those facts.

## 1. What there is today

### 1.1 On the screen

| File | What it holds | Pure (host test) | Hardware it touches |
|---|---|---|---|
| `picture_question.h` | the one question every owner asks, its JSON, the fields an older app reads, the numbers by which an answer finds its owner | yes, `tests/test_picture_question.cpp` | none |
| `picture_loader.h` | one route for every picture: who wants what, one download at a time, the most urgent first | yes, `tests/test_picture_loader.cpp` | none |
| `picture_store.h` | the pictures kept, within one budget, taken over from a download without a copy | yes, `tests/test_picture_store.cpp` | none |
| `tile_picture.h` | a tile's frame, key and question; a plugin tile's places as the parts of one picture | yes, `tests/test_tile_picture.cpp` | none |
| `camera_view.h` | the constants of asking and loading again (`REFRESH_MS`, `GAP_MS`, `ASK_AGAIN_MS`, `SETTLE_MS`, `tiles_seen`); its `Feed` went in step 1 | yes, `tests/test_camera_view.cpp` | none |
| `picture_jpeg.h` | the JPEG a screen takes: whole MCUs, the decoder's stride, the notes (`TSSR`) and the corners made exact; one profile with the app's `picture_paint` (step 2, done) | yes, `tests/test_picture_jpeg.cpp` | none |
| `picture_fetch.h` | the link, an answer's head, the BMP decoder row by row, the gatherer of a whole JPEG | yes, `tests/test_picture_fetch.cpp` | none |
| `picture_fetch.cpp` | the download task and its socket, the three slots, the hand-off to the main loop | no | sockets, FreeRTOS, PSRAM; a whole JPEG through `picture_engine` (step 4) |
| `live_view.h` | the stream's framing (`Reader`), where a rectangle lies on a turned panel (`on_panel`), how a picture fits or is cut (`fit`, `cut`), what a tile lays over a live picture (`compose`, `draw_loader`) | yes, `tests/test_live_view.cpp` | none |
| `glass.h`, `glass_dsi.cpp` | the panel as a surface (step 3, done): its size, format and turn, the frame buffer (a linker wrap of `esp_lcd_new_panel_dpi`), the one-writer lock with LVGL's refresh hooks, the rooms LVGL keeps out of (`keep_out`), the underrun counter, the PPA burst wrap | `on_panel`, `tests/test_live_view.cpp` | DSI panel, LVGL internals |
| `picture_engine.h`, `picture_engine_p4.cpp` | the engine (step 4, done): the formats taken whole, the hardware JPEG decoder for stills and streams, the PPA copy through the guard, the one turn mapping (`ppa_angle`); the software engine is the stubs | `ppa_angle` and the stubs, `tests/test_picture_engine.cpp` | JPEG decoder, PPA, 2D-DMA |
| `live_view.cpp` | the streams' tasks, the canvas of a tile and what goes over it, the camera's sound to the speaker | no | sockets, speaker |
| `ppa_guard.h`, `.cpp` | a turned PPA copy the 2D-DMA would never finish goes in pieces (DIG-734) | yes, `tests/test_ppa_guard.cpp` | PPA, through a linker wrap |
| `live_spots.h` | the one machine of the live tiles and a plugin's live places: what streams, asks, stops and gives up; the full view's handle and tries (`ViewStream`) (step 5, done) | yes, `tests/test_live_spots.cpp` | none |
| `runtime_tiles.h` (the picture parts) | the owners (the full view, the alert, the media card's cover, every tile, the library, a vacuum's map, a plugin's card and saver), the slots bound from YAML (`ImageHooks`), the store bound to PSRAM, `pictures_round`, the full view (`camera_open`, `camera_close`, `camera_answer`), what binds the live spots (which may stream, their question, their look), `drawn_over`, `live_stop_covered`, `live_tick` | no | LVGL |
| `plugin_host.cpp` (its picture parts) | a plugin's places measured and laid, `ui::picture`, `ui::set_picture`, `ui::live`; `tessera::capturing` reports to the dot | no | LVGL |
| `capture_dot.h` | the dot while the screen's own camera is in use, and the listener on that camera (step 6, done) | no | LVGL, ESPHome's camera API |
| `module_doorbell.cpp` | a ring's view over the camera full view | no | LVGL, speaker |
| `__init__.py` (`_p4`, `_engine`), `p4_build.py`, `engine_build.py` | on an ESP32-P4: the TCP window and the network buffers in PSRAM (`p4_build.py`); on every ESP32 the engine, the glass and the streams chosen by the chip, LVGL and PSRAM (`engine_build.picture_engine`: their defines, wraps and IDF components), LVGL bound to the glass where there is one (step 7, done) | `p4_build.py`, `engine_build.py`, `tests/test_live_view.py` | the build |
| `packages/features/camera.yaml` | binds the three slots to `picture_fetch` (`BOOT_CAMERA_HOOKS`), the 50 ms hand-off, `SCREEN_PICTURES`, `LV_USE_IMAGE`, `LV_USE_SNAPSHOT`, the alert's frame | | the build |
| `web/wasm/image_transport.h` | the editor's preview binding the same three slots to a fetch in the browser | | the browser |

### 1.2 In ESP Screen Manager

| Module | What it holds | Test |
|---|---|---|
| `picture_question.py` | the question read and checked, the caps, what a board can show (`BOXES` from `boards.json`), the answer | `tests/test_pictures.py` |
| `picture_legacy.py` | every older shape read into the same question | `tests/test_pictures.py` |
| `picture_sources.py` | the rules per source and owner (`may`), getting each source (`get`), the cameras' snapshots and the players' covers fetched once per camera in the screen's rhythm (`Snapshots`); what it reads of the app is `Providers` (step 8, done) | `tests/test_pictures.py`, `tests/test_camera.py` |
| `picture_paint.py` | one painter: fit, corners, shade, dim, turn, mirror, the atlas, and the three formats (`bmp8`, `bmp24`, `jpeg` with whole MCUs and the `TSSR` notes) | `tests/test_picture_paint.py` |
| `picture_links.py` | the links on the camera port, stills and recipes, the 304s | `tests/test_pictures.py` |
| `lan_address.py` | the app's address on the LAN the links carry (`base_url`, `lan_address`, the published port) (step 8, done) | `tests/test_camera.py` |
| `picture_service.py` | a question in, a link or a stream out; the painted pictures kept by what they show | `tests/test_pictures.py` |
| `plugin_pictures.py` | what a plugin's manifest allows its places; its addresses fetched and kept | `tests/test_plugins.py` |
| `camera_source.py` | a camera live: the source per camera (WebRTC or snapshots, its stills first), the sound resampled (step 8, done) | `tests/test_camera_source.py` |
| `live_pictures.py` | the JPEG per room (`Encoder`, `remake`, `size_for`, `size_to_cover`, `Pictures`) (step 8, done) | `tests/test_live_pictures.py` |
| `live_stream.py` | the MJPEG writer on the camera port, the links, `hold`, `live_pace` (step 8, done); `picture_service.stream_of` decides what streams and how it fits | `tests/test_live_stream.py`, `tests/test_pictures.py` |
| `rest_mosaic.py`, `alert_layout.py`, `media_library.py` (thumbnails) | sources that draw themselves, the alert's frame, the library's covers | their own tests |
| `ha_integration/tessera_video/` | the screen's own camera as a Home Assistant camera: its RTSP address and the password rule | `tests/test_screen_video.py` |
| `server.py` (`Manager`) | `answer_camera`, `camera_allowed`, `saver_entities`, `plugin_picture`, `saver_picture`, `thumbnail`, `map_render`, `rest_render`, `link_base`, the hello's `pictures` and `live` | |

### 1.3 In the Screen camera plugin

| Folder | What it holds | Hardware it touches |
|---|---|---|
| `components/esp_video_camera/` | a copy of the ESP32-P4 camera driver of ESPHome pull request 16944 (its NOTICE lists the copy's own changes): esp_video (V4L2) brought up with the sensors it auto-detects, the capture task, the mode negotiated as a string (`resolution`), an optional PPA transform (a turn, a scale down) for the JPEG path, the hardware JPEG encoder, two taps (`RawVideoFrameConsumer`, `JpegFrameConsumer`, one of each), ESPHome's camera API for Home Assistant's stills and streams, the sensor's exposure read for a consumer | MIPI-CSI, ISP, PPA, JPEG encoder |
| `components/sc202cs/`, `components/ov02c10/` | a sensor's black level, a sensor driver and its tuning that esp_cam_sensor lacks | I2C, the driver's own section |
| `components/screen_camera/` | the plugin: light level and motion from the frames on the camera's task, the dot (`tessera::capturing`), wake on motion; the frame hub every consumer takes the camera's frames from (`frame_hub.h`), the reader of a frame (`frame_reader.h`, `tests/test_frame_reader.cpp`) and the sensors the camera finds by itself (`sensors.py`) (step 9, done) | the camera's task |
| `components/screen_video/` | the part Video, one of the hub's consumers: a cut to whole macroblocks by the PPA and the H.264 encoder (`video_encoder.cpp`), the RTSP server with its viewers, RTP and RTCP (`rtsp_server.cpp`), the microphone as Opus (`opus_sound.cpp`), the memory rules (step 9, done) | PPA, H.264 encoder, sockets, microphone |
| `components/esp_h264_placeholder/` | an empty encoder for a build without the video | the build |
| `plugin.yaml`, `parts/video.yaml` | the camera in its JPEG mode, or in its raw mode with the video | |

### 1.4 The transports

Three ways a picture or a stream crosses a boundary, each with a contract both sides keep:

1. **The screen and the app**: the question as the event `esphome.screen_camera` (`q`, `n`, and the older fields), the
   answer as the screen message `op camera` (`t`, `n`, `u`, `m`), and the camera port (`/camera/<token>.bmp`, `.jpg`,
   `.mjpeg`: BMP 8 or 24 bits, the JPEG profile below, `multipart/x-mixed-replace` with `X-Picture: still` and
   `audio/x-s16le` parts).
2. **The screen and Home Assistant**: ESPHome's own camera API for stills and streams of the screen's camera (`camera::Camera`,
   `CameraListener`, `CameraRequester`), and, with the video, RTSP on port 8554 (user `tessera`, the password from the
   API key, RTP over the connection, H.264 as RFC 6184, Opus as RFC 7587) read by Home Assistant's `tessera_video`.
3. **The app and Home Assistant**: Home Assistant's camera proxy and media player proxy for snapshots and covers, its
   WebRTC offer and answer over the websocket for a camera's stream and sound, its states for what a camera is.

### 1.5 What is right already, and stays

- The question, the loader, the store and a tile's picture are pure and tested on a PC; every owner on the screen goes
  through them, and the app answers every question with one service, one painter and one link table. That is the
  spine, and this design builds beside it, not through it.
- The download slots (`ImageHooks`) are already an interface with three implementations: the device and the host
  renders (`picture_fetch`), and the editor's preview (`preview_images`). The refactor keeps it as the one way a
  picture's bytes reach the screen.
- `live_view.h` already keeps what a PC can check apart from the task, and `live_view.cpp` names its concerns in
  comments. The split below follows those comments.
- The plugin's sensor drivers already stand beside the camera driver, keyed on a sensor's id at run time; no board
  file names a sensor, only its bus and its clock pin.
- The password of the video is one rule in two places, and a test keeps them equal.

## 2. Seams, duplications and leaks

What was found reading the code, each with where it is. None of these is a bug a person sees; each is a place where a
change for one board or one chip would have to be made in a file that is not about that board or chip, or where the
same rule is written twice.

### 2.1 On the screen

1. **The download knows the P4's decoder.** `picture_fetch.cpp` includes `live_view.h` for `STILLS_JPEG`,
   `prepare_stills`, `still_input` and `decode_still`: whether a still may come as JPEG, where its bytes may land and
   who decodes it are the streams' business there, not a decoder's. A second chip with a hardware decoder, or a
   software JPEG decoder on an S3 one day, would be another `#if` in the download.
2. **The question's formats come from the presenter.** `runtime_tiles::picture_ask` adds `jpeg` to every question by
   `live_view::STILLS_JPEG`. What a screen's decoder takes is a capability of the decoder, and should come from it.
3. **`live_view.cpp` holds seven concerns in one file**: the panel (its handle, size, format, frame buffer, underrun
   counter), the one-writer lock and LVGL's refresh hooks, the keep-out of LVGL's areas, the stream client (the task
   that reads the MJPEG), the picture engine (the decoder and the PPA copy), the composition of a tile (canvas, shade,
   corners, name, loader) and the camera's sound to the speaker, plus the stills' decode service for the download. Each
   is well commented; none can be tested or replaced on its own.
4. **The JPEG decode is written twice** in `live_view.cpp`: `show()` and `decode_still()` set the same decoder
   configuration and do the same sums for the decoder's whole MCUs (rows rounded to 16 or 8).
5. **The JPEG profile is in four places.** That a JPEG for a screen is baseline 4:2:0 in whole MCUs of 16, that its
   shown size and its rounded corners travel in an APP15 segment `TSSR`, and that the screen makes those corners exact
   again, lives in `picture_paint.py` (`MCU`, `_whole_mcus`, `encode`, `corners_of`), `picture_fetch.h` (`jpeg_notes`,
   `mask_corners`), and twice in `live_view.cpp` (the stride sums). It is one contract, and no test keeps the sides equal.
6. **Three live state machines.** The full view's stream (`ViewPicture.live`, `live_wanted`, `live_begin`, the branch in
   `camera_answer` and in `live_tick`), the live tiles (`LiveTile`, `live_tiles_round`, `live_tile_answer`) and the live
   places of a plugin (`LivePlace`, `live_places_round`, `live_place_answer`) each keep asked, asked_at, failures,
   handle and streaming, ask again after `ASK_AGAIN_MS`, wait `GAP_MS` between asks, give up after `TRIES`, and stop when
   something lies over them. The tiles and the places are the same machine twice; the full view is a third copy with a
   room instead of a card. None is tested on a PC.
7. **`camera_view::Feed` has no user.** The loader replaced it (firmware 0.52.0); only its test and two comments name it.
8. **The shade's numbers are in two languages without a guard.** `live_view::FADE_PERCENT` and `FADE_DEPTH` must equal
   `picture_paint.FADE_SHARE` and `FADE_DEPTH` (a live tile lays over its frames what the app bakes into a still), and
   only comments say so, where `MAX_SIDE`, `MIRROR_PERCENT` and `MAX_PARTS` have a test each.
9. **The capture dot lives in the plugin host.** `CameraWatch` (ESPHome's camera listener), the users that capture and
   the dot itself sit in `plugin_host.cpp` between the plugin register and the cards. They are the screen's own
   "the camera is in use" rule, which the plugin API only reports to; a header of their own would say so.
10. **The P4 engine's build is spread.** What the P4 engine needs of the build (`USE_LIVE_VIEW`, the three wraps, LVGL
    bound) is in `__init__.py`, what it does with them in `live_view.cpp` and `ppa_guard.cpp`. Fine, but unnamed: the
    design names it.
11. **The turn's mapping is written twice, in two repositories.** The PPA counts its angles counter-clockwise where
    LVGL and ESPHome count clockwise: `live_view.cpp` (`copy`) maps 90 to the PPA's 270 and 270 to its 90, and the camera
    plugin's copy of the driver does the same in `ppa_rotation_for_clockwise`. The engine's `blit` takes the turn as LVGL
    counts it and maps once; the copied driver keeps its own, as a copy of an upstream must.

### 2.2 In ESP Screen Manager

12. **`Sources` leans on the whole Manager.** `picture_sources.Sources` takes `server.Manager` and reaches some twenty
    of its members (`layout_tiles`, `camera_allowed`, `saver_entities`, `map_render`, `map_meta`, `rest_render`, `rest_pools`,
    `thumbnail`, `shelves`, `photos`, `saver_choice`, `saver_picture`, `plugin_saver_kind`, `plugin_picture`,
    `plugin_picture_refused`, `followed`, `player_ground`, `device_entries`, `registry_index`, `ha.states`). The rules per
    source are tested, but only against a stand-in that mimics that whole object.
13. **`live_feed.py` is three things**: what a camera gives (`Source.run`, `webrtc`, `rtc`, `snapshots`, `stills_until`,
    `hear`, `heard`), what a screen gets of it (`size_for`, `size_to_cover`, `jpeg_size`, `remake`, `Encoder`, `Source.picture`,
    `make`) and how it travels (`Link`, `LiveFeed.serve`, the MJPEG writer, `hold`). `picture_service._stream` repeats the
    cover-or-contain decision in three branches.
14. **The camera port's module finds the app's address.** `picture_links.py` holds the link table and, beside it,
    `base_url`, `lan_address`, `_read_lan` and `published_port`: where the screens reach the app is a fact of the network,
    not of the links.

### 2.3 In the Screen camera plugin

15. **The frames are chained, not shared.** `esp_video_camera` takes one raw consumer. With the video on, the video is
    that consumer and hands every frame on to sensing (`ScreenVideo::consume_raw_video_frame` calls
    `ScreenCamera::consume_raw_video_frame`; `take_frames_from_video` switches sensing over). A third reader (a plugin
    that wants frames, a future intercom) would be a third link in the chain. A fan-out is missing.
16. **The camera's mode is a string and a table's order.** `resolution: auto` sends `VIDIOC_S_FMT` without a size and
    reads back what the sensor took: the first mode of its driver's table. The OV02C10 got a 1280 x 720 mode put first
    for the video; a larger sensor is to be told a smaller mode in the part's YAML. The consumers' needs (the encoder's
    whole macroblocks of 16 and at most 1280 x 800, the frame rate, sensing's smallest useful frame) are known to the
    code and not to the choice.
17. **The pipeline is a config word.** `device: jpeg` (RGB565 capture, the JPEG encoder on demand) or `device: csi`
    (YUV420 capture for the video) is set by the part's YAML, not decided from who consumes frames.
18. **The sensors the build knows are a list in Python** (`CONFIG_CAMERA_SC202CS`, `OV5647`, `SC2336` and the SC202CS
    tuning file in `esp_video_camera/__init__.py`), beside the OV02C10 that brings its own. Adding a sensor is a change
    in the copied driver's Python rather than a row in a table of the plugin's own.
19. **Sensing reads two pixel layouts itself** (`RGB565_LE` and the encoder's `O_UYY_E_VYY`) in the middle of its motion
    rule; a frame reader that gives the brightness of a point would keep the rule free of layouts.
20. **The video does three things**: the frame path (cut, encode), the server (viewers, RTSP, RTP, RTCP) and the sound
    (microphone, Opus, the clock). Each is bounded by comments, none by a file.

### 2.4 Board-specific code inside shared code

None by a board's name: `grep` finds boards only in comments that say where a number was measured. What is keyed on a
fact of the hardware, and where:

| Fact | Where it is read | Where it has effect |
|---|---|---|
| the chip is an ESP32-P4 | `__init__.py` (`_esp32_p4`, `_engine`) | `P4_NETWORK`; `PICTURE_ENGINE_P4`, `GLASS_DSI`, `USE_LIVE_VIEW` and the three wraps (`engine_build.py`) |
| the chip is an ESP32-S3 with PSRAM and LVGL | `__init__.py` (`_engine`) | `PICTURE_ENGINE_S3`, `GLASS_RGB`, `USE_LIVE_VIEW`, the esp_new_jpeg component and the wraps of its allocator and of `esp_lcd_new_rgb_panel` (`engine_build.py`) |
| how many live tiles at once | `picture_engine::limits().live_tiles` (four on the P4, one on the S3: each tile's Wi-Fi and lwIP buffers cost the S3 about 11 KB of internal RAM, CAMERA.md "Live on an ESP32-S3") | `hw::caps`, the hello, the editor |
| the pictures a second the live tiles share | `picture_engine::limits().tile_budget_pps` (24 on the P4, 8 on the S3), shared by `picture_engine::tile_pps` | each tile's pace (`live_view.cpp`, `tile_gap_us`) |
| the core a stream decodes on | `picture_engine::limits().stream_core` (1 on the P4, 0 on the S3, away from LVGL) | the stream's task (`live_view::open`) |
| whether a decode holds the glass, and a full view's pace | `picture_engine::limits()` (`decode_on_glass`: the P4's decoder runs on the 2D-DMA, the S3's on the CPU; `view_pps` 8 on the S3) | `live_view.cpp` |
| the panel is MIPI-DSI | `glass_dsi.cpp` (the wrap of `esp_lcd_new_panel_dpi`) | a P4 with an RGB panel would find no frame buffer and show stills |
| the panel is an S3's RGB panel | `glass_rgb.cpp` (the wrap of `esp_lcd_new_rgb_panel`, its frame buffer; no underrun count, `misses` 0) | an S3 with a SPI or QSPI panel finds no frame buffer and shows stills |
| LVGL draws big-endian | `glass_rgb.cpp` (`LV_COLOR_16_SWAP`, `glass::Panel::swapped`) | `picture_engine::Block::swap`, the S3's blit |
| the frame buffer is RGB565 | `glass_dsi.cpp` | `glass::direct()`, `live_view::available()` |
| each 2D-DMA client's burst | `picture_engine::limits().burst_bytes` (64 on the P4: the panel's bridge runs dry on ESP-IDF's 128, lvgl/lvgl #9590) | the streams' and LVGL's PPA clients (`glass_dsi.cpp`) |
| the largest picture a stream's part may be | `picture_engine::limits()` (`picture_bytes` 1 MB, `tile_picture_bytes` 384 KB on the P4, over a busy camera's 150 to 250 KB at 1280 x 800, CAMERA.md 2026-10-10; 0 elsewhere, no part at all) | `live_view::Reader`, a stream's input buffer |
| how the engine scales | `picture_engine::fit`, `cut` (the P4's PPA in sixteenths) | every copy's `scale`, which the shared code hands on and never counts in |
| the PPA scales YUV420 in eighths, writes the whole scaled block, and is one device | ESP-IDF 5.5.5 `esp_driver_ppa/src/ppa_srm.c`, read 2026-10-25: for YUV420 output the scale's fraction is made even (lines 301-305, `scale_x_frag & ~1`: an odd sixteenth runs as the even one below it while the output block was sized with the odd one, lines 229-240); the output block is the input block times the scale, floored (line 236), and one that does not fit the output picture is refused (line 242), so there is no "scale over and cut the overhang"; YUV420 blocks, pictures and offsets are even (lines 198-215) | Screen camera's video cuts in the PPA only (CAMERA.md, "The screen's own camera as video"): a scale pass of a 1280 x 720 frame took 77 to 89 ms and the live tiles' blits waited behind it |
| the chip is a pre-v3 P4 | `ppa_guard.cpp` (`block.mb = 16`, a comment on `CONFIG_ESP32P4_SELECTS_REV_LESS_V3`) | the guard's macro block |
| the Wi-Fi goes through a co-processor over SDIO | `__init__.py` (`P4_NETWORK`, keyed on the chip) | the TCP window and send buffer, the network's buffers in PSRAM |
| how the glass is turned | `live_view.cpp` (`turn_now`, LVGL's rotation, read at every tick: the app can stand a screen up at run time) | every copy's angle, a stream ended with `TURNED` |
| the board has PSRAM | `packages/features/camera.yaml` included or not (`SCREEN_PICTURES`), `picture_store::ENTRIES` | pictures at all |
| the board has a speaker | `packages/features/audio.yaml` (`bind_speaker`) | the camera's sound |
| the board has a camera sensor | the board file's `CAMERA_I2C`, `CAMERA_XCLK_PIN` (the feature `camera_sensor`) | the plugin's `esp_video_camera` |
| which sensor | the sensor's id over I2C at run time (esp_cam_sensor's auto-detect, `sc202cs`, `ov02c10`) | its driver and tuning |

The rule for a chip's fact: shared code reads it from `picture_engine::limits()`, `fit`, `cut` or a wrap, never from a
header of its own; outside the engine's files (`picture_engine*.h`, `picture_engine_p4.cpp`, `ppa_guard.*`,
`picture_jpeg.h`, `glass_dsi.cpp`) the code names no sixteenths, PPA, JPEG driver or MIPI panel, which
`tests/test_live_view.py` (ChipFactsBehindTheEngine) keeps so.

So the rule holds today. What the design adds is a place for each fact to be read once, so a new chip or panel kind is
one implementation beside the P4's rather than an `#if` in the shared files.

## 3. The layers on the screen

```
 owners: the full view, the alert, the cards, the tiles, the library, a plugin's places   (runtime_tiles, plugin_host)
   |  want / ask / answer                           |  live spots: what streams, asks, stops
 picture_loader  --  picture_store  --  tile_picture  --  picture_question         live_spots (new, pure)
   |  load / cancel / done                                                           |  open / close / events
 download transport: ImageHooks  ->  picture_fetch (device, host) | preview_images (editor)   live_view: the stream client
   |  decode rows (BMP)  |  gather whole (JPEG)                                      |  decode, compose, blit
 picture engine: formats, decode, blit          (new: engine_p4 = hardware JPEG + PPA + ppa_guard | engine_soft = BMP rows)
   |  under the glass lock
 glass: the panel's facts, its frame buffer, the one-writer lock, the rooms LVGL keeps out of   (new: glass_dsi | none)
```

The arrows point down only. A layer knows the one under it by its interface and nothing above it. The owners never
name a chip; the engine never names an owner; the glass never names a picture.

### 3.1 Glass: the panel as a surface

What the panel is and who may write it. On a P4 with a DSI panel it is today's `panel_made`, `frame_buffer`, `glass`
mutex, `hold_glass` and `release_glass` on `LV_EVENT_REFR_START` and `REFR_READY`, `keep_out` on `LV_EVENT_RENDER_START`,
`count_misses` and the burst wrap, moved into `glass.h` and `glass_dsi.cpp` as they are.

```cpp
namespace glass {
struct Rect { int x, y, w, h; };                      // as LVGL lays the screen out (live_view::Rect today)
struct Panel { int w = 0, h = 0; bool rgb565 = false; };
Panel panel();                                        // 0 x 0 while ESP-IDF made no panel for LVGL
int turn();                                           // LVGL's rotation, degrees clockwise
bool direct();                                        // a frame buffer a task may write past LVGL
void *frame_buffer();                                 // that buffer, panel.w x panel.h RGB565; nullptr without
void hold();                                          // one writer at a time: LVGL for a refresh, a task for a copy
void release();                                       //   (the recursive mutex of today, the same hold points)
using Room = int;                                     // a rectangle LVGL keeps out of while someone writes there
Room reserve(const Rect &area);                       //   (armed: today's `armed`, `spot`, `keep_out`, `invalidate`)
void move(Room room, const Rect &spot);
void give_back(Room room);                            //   LVGL draws the room again
uint32_t misses();                                    // the panel ran dry since boot
Rect on_panel(const Rect &r, int turn, int pw, int ph);  // pure, as today
}
```

Two writers reach the frame buffer, and the lock covers both. LVGL's refresh, which on a turned glass goes through
ESPHome's own PPA turn of each strip into an intermediate buffer in PSRAM (`rotate_buf_`) and then the panel's DMA copy,
holds the glass from `REFR_START` to `REFR_READY`; a stream's blit goes straight into the frame buffer and holds it for
each copy. `turn()` is read every time and never kept: the app can stand a screen up at run time (`LVGL_ROTATION`), and a
stream opened for the other turn ends with `TURNED`, as today. The turned P4 glasses (the boards whose file sets
`ROTATION_LANDSCAPE` to 90 or 270, and any screen stood up) draw with a 50 % LVGL draw buffer, so every strip LVGL
flushes is a turned PPA copy too; that is why the panel's share of the bus (the 64-byte bursts of every client) and the
guard hold for LVGL's copies as much as for a stream's.

May know: ESP-IDF's panel, LVGL's display and refresh events, the DSI bridge's underrun flag. May not know: pictures,
streams, JPEG, the PPA, owners. Without a direct frame buffer (every S3 and ESP32 board, the host renders, the editor's
preview) `direct()` is false and the rest are inline stubs that cost no flash.

### 3.2 The picture engine: decode, scale, turn

What turns bytes into pixels and pixels into other pixels. Two implementations, chosen when the firmware is built, as
the firmware chooses modules: `engine_p4` is the hardware JPEG decoder, the PPA with `ppa_guard` and the decoder's own
buffers (today's `decoder_ready`, `decode_still`, `still_input`, `copy`, the decoder calls in `show`); `engine_soft` is
the BMP decoder row by row (`picture_fetch::Decoder`, as it is) and no blit at all, since LVGL draws every still there.

```cpp
namespace picture_engine {
const std::vector<std::string> &formats();          // what this screen's decoder takes, best first
bool whole(const std::string &format);              // a format gathered whole (jpeg), not decoded as it streams (bmp)
bool ready();                                       // the decoder made, on the main loop (prepare_stills today)
uint8_t *input(size_t bytes, size_t *got);          // a buffer the decoder may read (jpeg_alloc_decoder_mem)
struct Still { int w = 0, h = 0, stride = 0; size_t bytes = 0; };
uint8_t *decode(const uint8_t *data, size_t length, Still &out);   // whole MCUs, RGB565 in LVGL's order; the caller holds the glass
struct Block {                                      // one copy: a block of `in` to x, y of `out`, scaled and turned
  const void *in; int in_w, in_rows, bx, by, bw, bh;
  void *out; size_t out_size; int out_w, out_h, x, y;
  int sixteenths; int turn;                         // the scale in sixteenths, the turn as LVGL counts it
};
using Client = void *;
Client client();                                    // a PPA client with the panel's burst (open today)
void drop(Client client);
bool blit(Client client, const Block &block);       // today's copy(), the guard included; the caller holds the glass
size_t held(Client client);                         // what a client's buffers hold of the picture budget
}
```

The 2D-DMA's own facts are the engine's and nobody else's: its units of 64 pixels for 16-bit output and 32 for 24- and
32-bit, its macro block of 16 rows on every P4 build ESPHome makes (`CONFIG_ESP32P4_SELECTS_REV_LESS_V3`), its FIFO of
1536 bits, and the turned block with a small leftover that it never finishes (DIG-734), as `ppa_guard` holds them. The
guard is proven on glass with every turned copy forced through its planner's cuts (ten thousand pieces in three minutes,
pieces one pixel wide among them, the chrome correct) and cleared as a cause of the restarts of October 2026 (the two
P4 screens that restarted decoded to a blocked main loop without a line of the guard; section 8 says what blocked it):
it is a block to keep, moved under the engine as it is, and the engine's `blit` is where every PPA call of the firmware
passes, the streams', LVGL's and a plugin's alike.

May know: the decoder, the PPA, the guard, the decoder's memory, the glass (to hold it is the caller's job, so the lock
points stay where they are). May not know: streams, sockets, owners, LVGL objects. The MCU sums of the JPEG profile
(section 3.7) are written once here.

### 3.3 The download transport, unchanged in shape

`ImageHooks` stays the interface between an owner's slot and whatever brings the bytes; `picture_fetch` stays the
device's and the host's implementation and `preview_images` the editor's. Two things change inside `picture_fetch.cpp`:
it asks `picture_engine::formats()` what to accept and `whole()` what to gather, and it hands a gathered JPEG to
`picture_engine::decode`. It includes `live_view.h` no more. `runtime_tiles::picture_ask` names the engine's formats in
every question instead of `STILLS_JPEG`.

### 3.4 The streams: live_view, the same outside, layered inside

`live_view`'s API stays as it is (`available`, `open`, `close`, `tick`, `mute`, `has_speaker`, `held_bytes`, `misses`,
the events), and so does the stream task's order of work. Inside, `live_view.cpp` keeps what is the stream's own: the
task, the socket, `Reader`, the canvas of a tile, `compose`, the loader over a still, the sound buffer and the speaker,
the reports. It calls `glass::hold` where it took the mutex, `picture_engine::decode` where it ran the decoder and
`picture_engine::blit` where it called `copy`, with the same arguments at the same lines. Nothing of the PPA's use or the
lock's reach moves or changes: the engine's `blit` is today's `copy` moved whole, `ppa_guard` is not touched, and the
keep-out, the arming and the spots keep their semantics in `glass`. That is the constraint while the restart hunt on
turned P4 glasses is open, and the design is drawn so it costs nothing to keep.

The stills' decode service (`prepare_stills`, `still_input`, `decode_still`) leaves `live_view` for the engine, where the
download reaches it without the streams between.

### 3.5 One live spot

The three state machines of section 2.1 item 6 become one pure header, `live_spots.h`, in the style of
`picture_loader.h`: what a spot is (the full view's room, a tile's card, a plugin's place), what it wants each round,
when it asks, what it does with an answer, when it stops, and what it hears of its stream.

```cpp
namespace live_spots {
enum class Kind : uint8_t { VIEW, TILE, PLACE };
struct Spot { Kind kind; uint32_t index; const void *place; std::string entity; glass::Rect room; bool contain; };
class Spots {
 public:
  std::function<uint32_t(const Spot &)> ask;                 // the question goes out; its number comes back
  std::function<int(const Spot &, const std::string &url)> open;  // live_view::open with the spot's look; -1 none
  std::function<void(int handle)> close;
  std::function<void(const Spot &, const char *what, const char *why)> log;
  void begin();                                              // every round
  void want(const Spot &spot, bool clear, uint32_t now);     // a spot that may stream this round
  void end(uint32_t now);                                    // what is not wanted stops; what is wanted asks in its turn
  void answer(uint32_t number, const std::string &url, bool clear);
  void covered(const Spot &spot, const char *why);           // live_stop_covered's verdict
  void event(int handle, live_view::Event event, uint32_t now);
  bool active(Kind kind, uint32_t index) const;              // asked or streaming (live_tile_active today)
  bool question(uint32_t number) const;                      // live_place_question today
};
}
```

`runtime_tiles` keeps `drawn_over`, `page_clear`, `card_room`, `live_area`, the look of each kind (`live_loader`, the
name's snapshot) and binds the callbacks; `tests/test_live_spots.cpp` drives the machine through fast page turns, an
answer that is no stream, a stream that fails three times, a turn of the glass and a spot that moved, as
`test_picture_loader.cpp` drives the loader.

As built (step 5): the tiles and the places are the one machine, `live_spots::Spots`, with the round protocol above. The
full view is not a spot of it: the loader asks for the view's picture and the stream comes back as that question's
answer, so forcing it into the round protocol would have changed when it asks. What it shares with the spots, the handle
and the tries of one opening, is `live_spots::ViewStream`, in the same header, with the same `TRIES`.

### 3.6 The owners and the loader

Unchanged. The owners say what they want, the loader decides, the store keeps. `camera_answer` keeps its dispatch by
`t`; the live branches call `live_spots::answer`.

### 3.7 The JPEG profile, named once

A header `picture_jpeg.h` holds the constants and the pure functions of the profile the app and the screen share: the
MCU of 16, the stride of a decoded picture for each sampling, the `TSSR` segment read (`jpeg_notes`) and the corners
made exact (`mask_corners`), moved from `picture_fetch.h`. `picture_paint.py` keeps its half. A test in
`tests/test_camera.py` keeps `MCU` and the `TSSR` layout equal between the two, as it keeps `MAX_SIDE`; another keeps
`FADE_PERCENT` and `FADE_DEPTH` equal to `picture_paint`'s.

### 3.8 The capture indicator

`CameraWatch`, the capture users and the dot move from `plugin_host.cpp` to `capture_dot.h`, with the same two entry
points (`watch_camera`, `capturing`). Optional: it changes no behaviour and no interface, only where the reader looks.

### 3.9 Which engine, decided by the build

`__init__.py` reads the facts and applies the engine; the C++ selects by define, as it does for modules. The facts and
the engines are a table in `engine_build.py` (free of ESPHome, `tests/test_live_view.py`), one row a chip, each with
three things that may come apart: the engine (`PICTURE_ENGINE_P4`: the P4's hardware JPEG decoder and the PPA;
`PICTURE_ENGINE_S3`: Espressif's software decoder on an S3 with PSRAM, stills only), the glass (`GLASS_DSI`: the P4's
MIPI-DSI frame buffer) and the streams (`USE_LIVE_VIEW`, which need an engine that copies pixels and a glass), with the
linker wraps and the IDF components each needs. Whether the display gave a frame buffer a task may write is a fact the
glass finds at run time (`glass::direct`), so a P4 whose panel ESP-IDF did not make as MIPI-DSI shows stills. How many
live tiles a screen streams at once is the engine's (`picture_engine::limits().live_tiles`). Another chip with its own
decoder is a `picture_engine_<chip>.cpp` and a row here; a panel kind a task may write is a `glass_<panel>.cpp` and its
own define; `picture_fetch`, `live_view`, `live_spots` and `runtime_tiles` see nothing of either. An RGB panel's glass,
for streams on the S3, is the next of these (docs/PLATFORM_PLAN.md 3.2).

What each layer may and may not know, in one table:

| Layer | May know | May not know |
|---|---|---|
| owners (`runtime_tiles`, `plugin_host`, `module_doorbell`) | LVGL objects, the model, the loader, the store, `live_spots`, `live_view`'s API, `picture_engine::formats` | the decoder, the PPA, the frame buffer, sockets |
| `live_spots` | time, the spots' rooms, the events of a stream | LVGL, hardware |
| `picture_loader`, `picture_store`, `tile_picture`, `picture_question` | as today: nothing of hardware | |
| download transport (`picture_fetch`, `preview_images`) | sockets, the slots, `picture_engine` | `live_view`, owners, the glass |
| `live_view` | sockets, `Reader`, the canvas and `compose`, `picture_engine`, `glass`, the speaker | which owner opened it, LVGL objects |
| `picture_engine` | the decoder, the PPA, `ppa_guard`, its memory, `glass::hold` as a rule for its callers | streams, sockets, owners, LVGL objects |
| `glass` | ESP-IDF's panel, LVGL's display events | pictures, the PPA, the decoder |
| `__init__.py` | the chip, the display platform, LVGL in the config | a board's name |

## 4. The layers in ESP Screen Manager

The app is layered already; three moves make the seams of section 2.2 explicit, with the tests moved along.

- **`picture_sources` takes `Providers`, not the Manager.** A small object of callables, assembled once in `server.py`
  from the Manager's methods, grouped by what a source needs: the layout (`tiles`, `camera_allowed`, `saver_entities`),
  Home Assistant's facts (`state`, `followed`, `player_ground`, `device_entries`), the drawers (`map`, `mosaic`, `vacuum`),
  the library and the photos (`thumbnail`, `shelf`, `photo`), the screensaver (`choice`, `step_picture`, `plugin_saver`),
  and the plugins (`picture`, `refused`). `Sources` reads nothing else; its tests build `Providers` with fakes instead of a
  stand-in Manager.
- **`live_feed.py` becomes three modules** along its own comments: `camera_source.py` (what a camera gives: `Source`,
  the WebRTC and snapshot routes, the stills first, the sound heard), `live_pictures.py` (what a screen gets of a frame:
  `size_for`, `size_to_cover`, `jpeg_size`, `remake`, `Encoder`, the pictures per room) and `live_stream.py` (how it
  travels: `Link`, `LiveFeed`, the MJPEG writer, `hold`, `live_pace`). `picture_service._stream` asks one function for
  the fit of a stream instead of deciding it three times.
- **Where the screens reach the app** (`base_url`, `lan_address`, `_read_lan`, `published_port`) moves from
  `picture_links.py` to `lan_address.py`; the link table keeps the links.

The three transports of section 1.4 stay as they are, byte for byte.

As built (step 8): `Providers` has one field per fact, named after what the Manager offers (`tiles`, `states`,
`mosaic`, `step_picture`, `plugin_refused` and the rest), and `Providers.of(manager)` binds each as a callable that reads
the Manager when it is asked, so a dict the Manager keeps is read as it is then and a method a test replaces is the one
called. The tests' stand-ins keep their names and go through `Providers.of`; `tests/test_pictures.py` also builds one
from fakes alone, every fact it does not hand in failing when read. The JPEGs of a camera's frames (`Pictures`) are
kept by `LiveFeed` beside each source, so `camera_source` knows no screen's room. The stream's fit is
`picture_service.stream_of`: the full view whole, a Live tile as its tile says, a plugin's place as its fit says. The
tests split along the modules (`tests/test_camera_source.py`, `tests/test_live_pictures.py`,
`tests/test_live_stream.py`) with every case kept, and the P4 build's check of the component joined `tests/test_live_view.py`.

## 5. The layers in the Screen camera plugin

```
 Home Assistant: stills and streams over ESPHome's camera API | the video over RTSP (tessera_video)
   |                                                          |
 consumers: HA stills (esp_video_camera's own), sensing (screen_camera), the video encoder (screen_video), a plugin one day
   |  frames, each at its own format and pace
 frame hub (new, in screen_camera): the camera's one consumer, fanned out
   |  raw frames on the camera's task
 camera source: esp_video_camera (the copy) + the mode chosen by capability (a marked change in the copy)
   |  esp_video, V4L2
 sensor drivers: esp_cam_sensor's own, ov02c10, the sc202cs black level     (as today, keyed on the sensor's id)
   |
 the board: CAMERA_I2C, CAMERA_XCLK_PIN, the sensor's power                 (the only lines a board file has)
```

- **The sensor drivers** stay what they are: a driver and its tuning beside the copy, found by the sensor's id. The
  list of sensors the build enables moves out of the copy's Python into a table of the plugin's own
  (`screen_camera/sensors.py`: id, the Kconfig options, a tuning file), read by `plugin.yaml`'s components; adding a
  sensor is a row, or a folder when esp_cam_sensor lacks it.
- **The camera source** is the copy of pull request 16944, with its changes marked and listed in its NOTICE as today.
  One change is added: `resolution: auto` chooses the mode by capability instead of by the driver's table. The chooser is
  pure (`camera_modes.h`: the sensor's modes in, the consumers' wishes in, one mode out: the largest every wish takes,
  then the one nearest the wished frame rate) and tested on a PC as Tessera's own headers are; the copy calls it in
  `configure_capture_format_` with the sensor's modes as esp_video enumerates them (`VIDIOC_ENUM_FRAMESIZES`, which
  esp_video 2.4 answers from the sensor's format table). The video's wish is whole macroblocks
  of 16 and at most 1280 x 800 at 15 frames a second; sensing's is at least 128 x 72; stills take any. An explicit
  `resolution` in the YAML stays an override, and the OV02C10's ordering stops mattering.
- **The frame hub** is the camera's one raw consumer, in `screen_camera`, and fans every frame out to the consumers
  that added themselves, each with the pixel format it reads and the pace it wants. Sensing and the video add
  themselves in their `setup()`; `take_frames_from_video` and the forwarding call go. A consumer reads a frame through
  a small `FrameReader` (brightness at a point, a row's pixels) so no consumer parses a layout itself.
- **The consumers** stay what they are: sensing (light and motion) and the video encoder. The video splits along its
  comments into the frame path (`video_encoder`: the cut by the PPA, H.264), the server (`rtsp_server`: viewers,
  requests, RTP and RTCP) and the sound (`opus_sound`: the microphone, the encoder, the clock), three files under
  `screen_video/` with one component and one YAML key as today.
- **The pipeline** stays `device: jpeg` or `device: csi` by the part's YAML in this round (section 6 says why).

As built (step 9, Screen camera 0.4.3): the frame hub (`screen_camera/frame_hub.h`) is the camera's one raw consumer;
the video adds itself in its setup with the encoder's YUV420 and is on from boot, sensing adds itself in its own setup
reading either layout and is on while the setting is, and the hub starts the camera when the first consumer is on and
stops it when none is, so the camera runs exactly as it did. Each consumer keeps its own pace. The sensors esp_cam_sensor
drives, and the SC202CS's tuning, are the rows of `screen_camera/sensors.py`, applied by that component with the same
Kconfig options and build file the copy set; the copy's NOTICE says so. The video's one class keeps its header and has
its code in three files by concern beside its life (`screen_video.cpp`). The plugin's rules raise its version with every
change and a changelog line under that version (its `tools/check.py` refuses an Unreleased heading), so this is 0.4.3.

The mode chooser is not built. esp_video 2.4 answers `VIDIOC_ENUM_FRAMESIZES` on the MIPI-CSI device with one entry,
the size the sensor runs at now (`common_video_enum_framesizes`, index 0 only), not the sensor's table, and the mode a
sensor starts in is esp_cam_sensor's own default (a Kconfig choice for the SC202CS, the first row of the OV02C10's
table). Choosing by capability needs the sensor's format array (`esp_cam_sensor_query_format`, which esp_video does not
hand out through V4L2) and `VIDIOC_S_SENSOR_FMT` to switch the sensor and the ISP before the stream starts: a change in
how the camera comes up, to be measured with both sensors on real glass (the OV02C10 on a Guition 10.1, the SC202CS on a
D1001), in a round of its own.

What each may and may not know: a sensor driver knows I2C and its registers, never a consumer; the camera source knows
esp_video, the PPA for its own transform and the modes, never who watches; the hub knows frames and consumers, never
what a consumer makes of them; a consumer knows frames through the reader and its own encoder, never the sensor or the
bus; the transports know their protocol and a consumer's output, never the sensor. Nothing in the plugin names a board;
the README may.

## 6. The refactor, step by step

Each step is one commit on dev, with no change in what any screen shows, and is proven before the next: every
`tests/*.cpp` and the Python tests, `tools/check.sh`, `tools/check.sh --firmware --affected` for the boards the step
reaches, the WASM preview's tests, and a flash on a reTerminal D1001 over USB for every step that touches the P4 path,
looking at the moments the step moves: a live tile starting and stopping under a card, the camera full screen with its
sound, a still as JPEG, a plugin's live place, the doorbell's view, the screensaver's photo. The 4 MB boards' flash use
is checked by the firmware check at each step; the engine's stubs are inline and must cost them nothing.

1. **`camera_view::Feed` goes**, with its test and the two comments that name it. Pure; `tests/test_camera_view.cpp`
   keeps the constants' checks.
2. **`picture_jpeg.h`**: the profile's constants and pure functions moved from `picture_fetch.h`; the stride sums of
   `live_view.cpp` call them; the equality tests with `picture_paint.py` (the MCU, `TSSR`, the shade's numbers).
3. **`glass.h` and `glass_dsi.cpp`**: the panel's facts, the frame buffer, the lock, the hooks, the keep-out, the
   misses and the burst wrap moved out of `live_view.cpp` as they are. `live_view.cpp` calls them. Proven on the D1001:
   the name never over a live tile after the full view closes, nothing of LVGL under a stream, the full view's top bar
   gone with it, the counts in the reports.
4. **`picture_engine.h`, `picture_engine_p4.cpp`**: the decoder and the PPA copy moved out of `live_view.cpp`, the
   stills' service with them, `decode` written once. `picture_fetch.cpp` depends on the engine, `picture_ask` names its
   formats. `tests/test_picture_engine.cpp` checks the software engine (formats, `whole`, a BMP through it) and the
   pure sums; the P4 engine is proven on the D1001 (stills as JPEG on tiles, the full view and the screensaver; two live
   tiles beside the full view; the reports' decode and lay-out times as before).
5. **`live_spots.h`**: the one machine for the full view, the tiles and the places; `runtime_tiles` binds it; the three
   copies go. `tests/test_live_spots.cpp`. Proven on the D1001 with the same moments as step 3, and a plugin's live
   place (`picture_frame` with `ui::live`).
6. **`capture_dot.h`** (optional): the indicator out of `plugin_host.cpp`. Proven by the dot on the D1001 while Home
   Assistant takes a picture and while sensing runs.
7. **`__init__.py`**: the facts named (`_picture_engine`), the define kept; docs/PICTURES.md and docs/CAMERA.md point at
   this page for the layers; AGENTS.md's table gets a row for the engine and the glass.
8. **The app**: `Providers` for `picture_sources`; `live_feed.py` into its three; `lan_address.py`. The tests split with
   them; `tests/test_pictures.py` and `tests/test_live_feed.py` keep every case.
9. **The plugin, on its dev branch** (both indexes, as its README says): the frame hub and the reader; the sensors
   table; the mode chooser with its test and the marked change in the copy; the video's three files. Screen camera
   stays at its version with a changelog line under Unreleased; the plugin's `tools/check.py` and a build of the D1001
   with the plugin and its video, looked at in Home Assistant (stills, the video with sound, light level and motion).

Not in this round, each a change in behaviour for a round of its own with a measurement on the bench: one YUV420
capture for stills and video alike (the JPEG encoder on demand from the same frames, so the part Video stops changing
the camera's mode); a software JPEG decoder for the S3 boards; the legacy question fields' removal (docs/PICTURES.md,
"Compatibility"); runtime switching between engines, which nothing needs; the budgets and the viewer model of section 8
and the diagnostics of section 9, which the layers make room for and which each need a measurement of their own.

## 7. What is left to decide

- The names: `glass`, `picture_engine`, `live_spots`, `picture_jpeg`, `capture_dot`, `camera_source`, `live_pictures`,
  `live_stream`, `lan_address`, `frame hub`, `camera_modes`.
- Whether steps 5 (the one live spot), 6 (the dot) and 8 (the app's three moves) go in this round or wait: each is
  independent of the others and of the engine.
- Whether the video's viewer model (section 8) goes before the refactor, as the fix for the viewer storm a tester's
  Guition 10.1 shows, and whether the integration's route for stills is checked first.
- Where the mode chooser is called: in the copy of the camera driver as a marked change (the sensor's modes are known
  only once esp_video is up, inside the copy's setup), or in a component of the plugin's own that the copy hands the
  modes to through one added call. Both keep the copy's NOTICE honest; the second keeps the copy smaller.

- Whether the video's cut of a camera a few pixels over the stream (the Guition's 1288 x 728, a PPA pass of about 60 ms
  a frame) goes away by letting the H.264 encoder read the window itself: esp_h264 1.3.8 has no stride in its public
  input (`esp_h264_enc_in_frame_t` is a buffer and a length), but the YUV input's 2D-DMA descriptor is set in
  `esp_h264_enc_hw_cfg_dma_yuv_bs` (hw/src/esp_h264_enc_hw_param.c, 491-497, `ha` = the picture's width), a function
  of another file than its caller, so a linker wrap could give it the camera's stride and the window's start. Possible
  with a wrap of internal API; not built.

## 8. Budgets and back-pressure

What a screen may take on at once is a set of numbers spread over files today: the picture budget (a fifth of the
PSRAM, at most 6 MB, `pictures_kept`), the streams' share of it (`live_view::held_bytes`, at most half), seven streams
a screen (`live_view::MAX_STREAMS`) and eight an app (`live_stream.MAX_STREAMS`), a stream's part of at most 1 MB, the
video's floor of internal RAM (`screen_video` skips frames under 80 KB and starts again above 110 KB), the TCP window
and send buffer of a P4, and nothing for the sum. A tester's Guition 10.1 with one live tile (360 to 480 KB a second
in), the video (out), the wake word and the Bluetooth proxy ran the Wi-Fi co-processor's driver into its wedge
(`H_SDIO_DRV: task still writing Rx data to queue!`, esp_hosted 2.12.12), with internal RAM at 60 to 80 KB and the wake
word's ring buffer overrunning.

What those restarts were, once the main loop's stack was kept across a watchdog (section 9): the loop blocked in a
synchronous call to the Wi-Fi co-processor (`wait_for_sync_response` in esp_hosted's RPC; which call is not yet known:
the power-save calls of the standby and the wake in `screen_power.h`, the signal strength every ten minutes and
ESPHome's own Wi-Fi calls are the candidates) while the C6's answer never came, because the SDIO receive path drops a block when its copy task is still busy with the last one
("task still writing Rx data to queue!", esp-hosted-mcu #197); the call waits the RPC's 5 seconds, ESPHome's task
watchdog was 5 seconds too, and the watchdog won. Measured on a reTerminal D1001 with two live tiles (345 and 140 KB a
second in; the larger one 10 pictures a second of 744 x 408, 87 ms of glass work each, the two together 1.3 seconds of
glass work a second): the receive side fell behind the pictures. dev answers it in two steps: the task watchdog of every
P4 board is 20 seconds (`packages/hardware/esp32p4-c6.yaml`), so a lost answer is a failed call and a 5-second stall of
the main loop, not a restart; and this section, which keeps the load from getting there. So the inbound rate is bounded
by the SDIO link and the glass work per picture, not by the decode, and a synchronous Wi-Fi call from the main loop is a
5-second stall under load: the two calls of the standby's doze belong off the loop.

The limits go in one place, `budgets.h`, worked out at boot from facts and never from a board's name:

- **the PSRAM**: the picture budget, as today, and the streams' share of it;
- **the internal RAM**: one floor every consumer of it honours (the streams' tasks, the video, the download), below
  which a part is dropped rather than taken, as the video does already;
- **the Wi-Fi path**: an inbound rate for the streams together, from the path's kind (a co-processor over SDIO gives
  about 2.6 MB/s on a P4 to one download, and far less to several streams beside the RPC's answers; an S3's own radio
  less again) and a share of it that is the streams', as a share of the PSRAM is;
- **the glass work**: the lay-out cost of a picture of a stream's size (the engine's copies, measured in the stream
  reports), so that two streams together never take more of each second than the main loop can spare;
- **the streams at once**, from the four above rather than a constant.

Every layer asks the budget instead of carrying a number. `live_view::open` refuses a stream that would take the inbound
rate over its share, and the owner shows stills, as it does today when the seventh stream is taken. A stream's task
drops a part when internal RAM is under the floor and says so in its report. The screen's question carries its stream
budget beside `live` (as `cap` carries the picture's), so that `live_stream` sends a screen under load fewer pictures a
second rather than the screen's Wi-Fi driver drowning in them, and fewer still while two streams are up; the
back-pressure the app has (the next picture is made once the last has left the host) stays, and the screen's own say
is added to it.

The video needs a viewer model that cannot be driven into a storm. Today a viewer is a connection, three may play, and
nothing keeps one peer from opening and closing one every second (the tester's log: "A viewer watches (one more)" dozens
of times in 45 seconds, then every second). In the model a viewer is a peer address with one session; a session opened
again within a cool-down of its own closing is refused with 503 and logged once with the address; and the stills Home
Assistant asks for cost no session each. The first thing to check there is the integration's own route for a still:
`async_camera_image` in `tessera_video/camera.py` falls back to ffmpeg when go2rtc gives no still, and ffmpeg opens an RTSP
session for every still a dashboard asks for, which fits the log and is to be verified on the tester's Home Assistant
before anything is built.

## 9. Diagnostics the layers make room for

Three gaps the restart hunt of October 2026 ran into, each a round of its own after the refactor:

- **A snapshot that shows live pictures.** `ui_snapshot` (packages/features/snapshot.yaml) renders LVGL's tree, so a
  live tile is a black room in it and a live picture cannot be seen from afar. With the glass a layer, a snapshot on a
  P4 reads the frame buffer under the glass lock, the truth of what the panel shows; a board without a direct glass
  keeps LVGL's render.
- **A record of what the loop waited on.** A task watchdog with an idle program counter says the main loop was blocked,
  not on what: the crash record (`esp32.crash`) keeps the program counter and two frames of the crashing core's task,
  and an abort keeps the assert machinery; the assert's text and the watchdog's culprit go to the console only. dev has
  the first piece (`loop_record.h`, `loop_record.cpp`, 2026-10-24): at a task watchdog the main loop's stack, every word
  that points at code, is kept in memory that survives the restart and logged at the next boot, decoded by the
  troubleshooting report; it is what named the C6's RPC above. The generalisation is a record per watched task, and
  beside it what the engine and the glass know: the last copies, each with its block's size, angle, scale and client,
  and who holds the glass and since when, so a stall on a copy says which copy and a lock held too long says by whom.
- **The stream reports as the one place for the counts**: the panel's misses, the decode and lay-out times, the parts
  dropped for the floor, the inbound rate against the budget, so a tester's log answers whether a change helped
  without a console on the board.
