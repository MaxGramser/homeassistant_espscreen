# The blue flash on the ESP32-P4 screens: what we know, 2026-10-30

A whole frame of light blue, one frame long, now and then, on the reTerminal D1001 and sometimes on the Guition
10.1 (JC8012P4A1 v3). Not fixed. This note holds everything measured so far, what was ruled out, what helped, the
two or three candidates that are left, and the bench experiment that decides between them. For a fresh session.

## The symptom

- One frame, the whole glass, light blue. Max sees one or two a minute on a page with four or five live camera
  tiles, more while the screen's own camera streams to another screen, and on the 10.1 when he leaves a live tile
  and switches pages while the camera streams. On pages without live tiles: never.
- Both boards are turned glass: a portrait panel, the UI rotated a quarter through the PPA (the P4's picture engine)
  into the frame buffer. The Tab5 (also turned) has not been reported with it.
- It never happens on the bench Guition without the encoder running; it needs load.

## The hardware chain (what the frame travels through)

1. LVGL draws into its buffers (internal RAM or PSRAM; the hot ones must stay out of PSRAM, see
   docs/PLATFORM_PLAN.md and the memory "PSRAM shares its bus with the DSI panel").
2. The PPA copies and turns each dirty area into the frame buffer in PSRAM (components/smart_display/glass_dsi.cpp,
   glass::hold/disarm, ppa_guard for the DIG-734 hang).
3. The DSI bridge (ESP-IDF esp_lcd_panel_dpi / mipi_dsi_brg) fetches the frame buffer from PSRAM with DMA, line by
   line, continuously: a panel has no memory of its own, every frame is re-sent.
4. The bridge feeds the DSI host, which serialises it to the panel (JD9365 on both boards).

Everything else on the PSRAM bus competes with step 3: the H.264 encoder (screen_video, reads camera frames and
writes the stream), the camera's CSI/ISP writing frames (5 fps at rest, more when watched), the JPEG decoder of the
live tiles, the PPA copies, the Wi-Fi chip's SDIO buffers (esp_hosted, CONFIG_ESP_HOSTED_MEMPOOL_PREFER_SPIRAM).

## Panel timing, both boards

| | reTerminal D1001 | Guition 10.1 |
|---|---|---|
| Pixel clock | 80 MHz preset, 70 MHz since 4547c4ae | 54 to 60 MHz |
| Refresh | 68.6 Hz, 58.9 Hz since 4547c4ae | about 50 to 60 Hz |
| Lane rate | 1.5 Gbps | 0.75 to 1 Gbps |
| Line | 800 + 20 + 20 + 40 = 880 pixels (896 with porch 56) | |
| Frame | 1280 + 12 + 4 + 30 = 1326 lines | |
| Chip | pre-v3 (rev 1.3), 360 MHz, PSRAM hex 200 MHz | rev3, 400 MHz, PSRAM hex 200 MHz |

The D1001's panel pulls a third to a half more from PSRAM than the Guition's for the same picture; it is the board
that shows the flash most.

## What was measured (dates, commits)

- 2026-10-25: hot LVGL buffers in PSRAM gave blue frames; moved to internal RAM (memory "PSRAM bus rule").
- 2026-10-27/28: on the bench Guition, a one-frame flash came with log writes; Debug mode (3574f2db) made screens
  quiet by default. The mechanism behind "log line = flash" was never found; it is the same symptom.
- 2026-10-29, the panel watch (b22b4d2c, glass_dsi.cpp): the DSI bridge's underrun flag read and cleared in the
  panel's on_vsync callback each frame, counted as "dry frames" and "flashes", HA sensors "Panel watch" and "Panel
  misses". Important detail: ESP-IDF masks the flag for an underrun in the first `h_size` lines
  (fifo_underrun_discard_vcnt = 800 of 1280), exactly the underruns that blue most of the glass; f35a1303 set the mask
  to 0 so every underrun counts. Before that the count saw only the lower-tile blue (39 to 53 a minute with the
  encoder's strip in PSRAM, PLATFORM_PLAN 4.4a).
- 2026-10-29 evening, Max's eye beside the count on the D1001, page with five live tiles, own camera streamed to the
  10.1: one or two whole-glass flashes a minute, panel watch "quiet, 4039 to 4046 frames a minute", misses 0. So the
  bridge raised no underrun flag for the frames Max saw. (Or the count missed them, see candidate 3.)
- Porch 56 alone (b579e383, the DSI host line a whole number of lane byte clocks, 2062.5 -> 2100): refuted by eye,
  reverted (b9468529). The arithmetic stands (ESP-IDF 5.5.5 mipi_dsi_hal.c host_dpi_set_horizontal_timing rounds
  htotal * lane_rate / pclk / 8), it just is not the cause.
- Own camera path: replacing the own-camera tile by another screen's stream still flashed. Not the capture path.
- Encoder idle (the 10.1 no longer pulled the tablet's video): "flashes less often", not never.
- Pixel clock 70 MHz with porch 56 (test branch, then 4547c4ae): no flash in a quarter of an hour on the same page
  and load, 3536 frames a minute. Later that night and the next morning Max still saw one now and then, on the D1001
  and the 10.1, mostly with the own camera streaming out and page switches. So less bandwidth helps and does not end it.
- Internal RAM on the D1001 fell from 284 to 140 KB in 18 minutes with the encoder and sensing running, largest block
  49 to 40 KB; with the video to the 10.1 running it sat at 143 KB. Not tied to the flash yet, but note it.

## Ruled out

- An underrun the bridge reports (count 0 with the mask off while the flash was seen).
- The DSI host line rounding (porch alone changed nothing).
- The screen's own camera capture path (another stream in its place flashed the same).
- Wi-Fi signal (both boards at -26 to -39 dBm).
- The viewer side of live tiles (page tiles stop under a full view; a full view never pauses for the governor).

## Candidates left

1. **The bridge covers a late fetch without raising the flag.** When the PSRAM fetch for a line comes too late, the
   bridge's FIFO runs dry; the datasheet says it discards the rest of the frame and the panel shows its "no data"
   colour, which is the blue. The flag should go up. If a code path (ESP-IDF's own handling, or the discard restart)
   clears it before our callback reads it, we count nothing while the panel shows blue. Fits: only under bus load, one
   frame, fewer with less panel bandwidth.
2. **A buffer swap before the PPA finished.** On turned glass every area goes through the PPA into the frame buffer.
   If the bridge starts a frame from a buffer whose rotation copy is still in flight because the PPA waited on the
   bus, the panel shows what was there. Fits Max's 10.1 observation: leaving a live tile and switching pages are the
   biggest PPA copies, with the encoder on the same bus. Does not fit as well: the frame should then show the old
   page, not a uniform blue; unless the buffer was cleared first.
3. **The count misses the frames that go wrong.** On pre-v3 silicon the on_vsync callback is "a fake vsync end": the
   end of the panel's DMA of a frame (esp_lcd_panel_dpi.c). A frame the bridge discarded may end its DMA differently
   and skip the callback, so the flag is read a frame later or never. Then candidate 1 is simply true and our proof
   "0 dry frames" is wrong. Cheap to test: log the raw register in the ISR every frame, and count frames against the
   refresh rate (4046 a minute at 68.6 Hz is 4116 expected; 3536 at 58.9 Hz is 3534: the count is a few percent low
   at 68.6 Hz, which is worth explaining).

## The deciding experiment (bench, one evening)

Setup: the bench Guition 10.1 (or the D1001) with Screen camera streaming to the add-on (a viewer on another screen
or go2rtc pulling it), four live tiles on page 1, Debug mode on. A script that switches pages every few seconds
(the API: page keys, or an automation that calls the screen's page service).

1. In the panel watch ISR (glass_dsi.cpp): read and log the bridge's raw interrupt/status registers every frame for a
   minute (ring buffer, dumped on the main loop), not just the masked underrun bit. Count frames against the panel's
   refresh to see whether frames go missing from the count (candidate 3).
2. Add a counter "frame started while a PPA job for the frame buffer was still running" (glass::hold / the ppa_guard
   know when a job is in flight; the ISR knows the frame start). If it ticks exactly when Max sees blue: candidate 2.
3. If neither shows anything while the eye sees blue: lower the panel's DMA competition one consumer at a time with
   the pclk kept at 70 MHz: encoder off, camera sensing off, tiles to two, Wi-Fi buffers back to internal RAM. The
   first one that ends the flash names the bus hog.

Fixes by candidate: (1) raise the DSI bridge's DMA/AXI priority, or a larger bridge FIFO threshold if the chip has
one, or keep the panel's bandwidth share by throttling the encoder when the panel is at risk (the governor already has
the works order: GLASS first); (2) wait for the PPA before the swap, or double-buffer the frame and swap only on a
finished copy; (3) fix the count first, then (1).

## Pointers

- components/smart_display/glass_dsi.cpp: the panel watch, the wrap of the panel's creation, the underrun mask.
- components/smart_display/glass.h: hold/disarm, misses(), watch_said().
- components/smart_display/ppa_guard.*: the PPA jobs and the DIG-734 guard (rev3: 32-row blocks).
- components/smart_display/pressure.h: the governor (GLASS > VOICE > DOORBELL > LIVE_TILES > OWN_CAMERA > SENSING).
- packages/boards/reterminald1001.yaml: pclk_frequency 70 MHz and hsync_front_porch 56, with the arithmetic.
- components/mipi_dsi_v3/models/seeed.py and guition.py: the panel presets.
- tessera-plugins plugins/screen_camera/components/screen_video: the encoder and the RTSP sender.
- Memory files: tessera-blue-flash-dsi-line-rounding, tessera-blue-flash-next-experiment, tessera-p4-psram-bus-rule,
  tessera-blue-flash-underrun-mask, tessera-blue-flash-live-tiles.
- Outside: espressif/esp-idf #19188 (the same flash with the flag silent), jtenniswood/espcontrol #2118.
