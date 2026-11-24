# Open issues: what we do not understand yet

One file per thing that is not solved: a symptom nobody can explain, a limit we hit, a bug without a fix. Each file
holds what was measured (dates, commits, numbers), what was ruled out, the candidates left, and the next experiment
that would decide, with pointers to the code. The point is that anyone, a contributor or a fresh session, can pick
one up without the person who found it, and that a release never forgets what it left open.

Rules:
- A new file when something stays open at the end of a day's work, with the same headings as the others: the
  symptom, what we know, ruled out, candidates, the deciding experiment, pointers.
- Keep it current: a measurement or a refuted candidate goes in the file in the same commit as the change it came
  from, with its date. A solved issue gets its last section "Solved" with the commit, and stays here a release long
  before it goes (the CHANGELOG keeps the story).
- Look here now and then (AGENTS.md says when): between releases, when a bench is free, or when a report from a user
  rhymes with one of these.

| File | What | Since |
|---|---|---|
| [module-files-asked-for-on-a-direct-link.md](module-files-asked-for-on-a-direct-link.md) | A page opened straight on a screen asks for the module lists and files of the other screens' plugins (the overview's previews ask before they leave): a few small requests once a day per browser, nobody sees it; the one change of order that fixes it and its test | 2026-11-24 |
| [alert-in-standby-dims-twice.md](alert-in-standby-dims-twice.md) | An alert that arrived in standby left the page behind its card dimmed twice in the light look, on a board with the dim on the glass: `screen_motion::show` now lets LVGL finish drawing first. Solved 2026-11-24, to be seen on glass | 2026-11-24 |
| [standby-by-hand-answers-a-ring.md](standby-by-hand-answers-a-ring.md) | Sleep, the board's key or the home button held during a doorbell's ring closes it as `closed`, which the app counts as an answer: the ring ends on every screen and Home Assistant hears it answered; the two readings and what would decide | 2026-11-24 |
| [plugin-modules-with-esphome-entities.md](plugin-modules-with-esphome-entities.md) | Eleven plugins keep their placeholder in the editor: their plugin.yaml makes ESPHome entities, and a module does not run the component's code generation; what the road needs, waste_collection as the first proof | 2026-11-24 |
| [phone-save-in-the-dock.md](phone-save-in-the-dock.md) | Save in the phone editor's dock does nothing for some phones in Home Assistant's app (GitHub #438); not reproduced, what was read and tried, what to ask | 2026-11-24 |
| [first-save-after-a-grid-change.md](first-save-after-a-grid-change.md) | A screen never saved refuses a grid change at its first save (GitHub #355); only the message changed on 2026-11-24, the fix in the file is not built | 2026-11-24 |
| [pictures-ahead-on-a-tight-store.md](pictures-ahead-on-a-tight-store.md) | Pictures fetched ahead use spare room only since 2026-11-24 (GitHub #415): proven on the host with the issue's numbers, not yet on a 7-inch with a store of about 1 MB | 2026-11-24 |
| [dark-mode-half-switched.md](dark-mode-half-switched.md) | Dark mode, a card or a turn that reached the glass only in part since 0.4.98: page pictures' copies of the frame buffer threw away what LVGL drew; removed. Solved 2026-11-19 for the P4 boards; a 4-inch report still open | 2026-11-18 |
| [esphome-2026-11-audio-stack.md](esphome-2026-11-audio-stack.md) | The boards with echo cancelling did not build on ESPHome 2026.11 (the speaker's `audio_dac_` became `audio_dacs_`). Solved 2026-11-19: the stack from a fork with one commit, until the stack has it | 2026-11-18 |
| [calls-found-on-the-bench.md](calls-found-on-the-bench.md) | Calls on two boards: the first call after a restart can stall, a sound takes a second there and back, the canceller relearns for a minute after two boards shared a desk, the Guition's microphone is noisy, a live view aborts when internal RAM runs out, and one old-protocol message leaves a screen at "Configuration problem" | 2026-11-17 |
| [waveshare-7-inch-rev3.md](waveshare-7-inch-rev3.md) | The Waveshare 7-inch P4 has no proven rev3 firmware: its old advice (`engineering_sample: false`) was not enough on the 10.1; what a report from a rev3 owner needs | 2026-11-16 |
| [main-host-render-min-power.md](main-host-render-min-power.md) | main's host render does not build on ESPHome 2026.9.0 (set_min_power without power scaling); fixed on dev by df32c78b, one line for a hotfix. Solved on dev 2026-11-16 | 2026-11-16 |
| [loop-stack-margin.md](loop-stack-margin.md) | The loop task's stack: a Guition 10.1 with a large layout overflowed it; fixed in b8e887c6, three boards read about 10 KB free; the screensaver and a night are still to read | 2026-11-16 |
| [page-pictures-step-two.md](page-pictures-step-two.md) | A page's picture is on the glass in 47 ms, but LVGL still draws the whole page after it (296 ms until it is done); what letting LVGL skip it takes. Solved: page pictures removed 2026-11-19 | 2026-11-16 |
| [lvgl-replace-style-selector.md](lvgl-replace-style-selector.md) | LVGL 9.5's lv_obj_replace_style with LV_PART_ANY \| LV_STATE_ANY overwrites each replaced style's selector; the report LVGL could get, not sent | 2026-11-16 |
| [card-look-on-glass.md](card-look-on-glass.md) | A card's look (sections whose tiles follow the contrast) is proven on the host and in the preview, not yet seen on glass; the file holds what to look at | 2026-11-15 |
| [render-swipe-past-excluded-pages.md](render-swipe-past-excluded-pages.md) | Host render checks that failed on dev: the swipe past excluded pages, automation, remote and bars. Solved 2026-11-16 | 2026-11-15 |
| [binder-still-large.md](binder-still-large.md) | runtime_tiles.h went from 14,333 lines to 4,550 in thirty-three parts; what is left in it, and server.py, still want cutting | 2026-11-16 |
| [sections-left-open.md](sections-left-open.md) | What sections leave open: their price in the memory budget and the receiver untested on its own (the header height: solved) | 2026-11-15 |
| [slow-single-cards.md](slow-single-cards.md) | A scene card draws in 17 to 18 ms and a light card once in 44 ms, where most cards take 2 to 8; a 2 x 2 player's 33 ms went with the page built from the loop, its paint still sets every value again | 2026-11-17 |
| [camera-tile-picture-left-on-the-next-page.md](camera-tile-picture-left-on-the-next-page.md) | A camera tile's last picture stayed on the next page where that page drew nothing; a redraw at the stream's end is in, not yet proven | 2026-11-15 |
| [veil-holds-an-s3-loop.md](veil-holds-an-s3-loop.md) | The dim laid on the glass holds an ESP32-S3's main loop about 60 ms, over the 50 ms limit, and the governor steps down for a moment | 2026-11-10 |
| [p4-panel-underrun.md](p4-panel-underrun.md) | A real underrun of the panel on an ESP32-P4: one counted flash now and then (GitHub #379), not reproduced on the bench | 2026-11-09 |
| [own-camera-tile-blit-cost.md](own-camera-tile-blit-cost.md) | A tile of the screen's own camera costs 50 to 60 ms of the PPA a frame, which limits every tile beside it | 2026-11-09 |
| [addon-webrtc-loss-on-yellow.md](addon-webrtc-loss-on-yellow.md) | On a Home Assistant Yellow the add-on loses WebRTC packets of the biggest stream when a full view runs: the asyncio loop near one core | 2026-10-29 |
| [full-view-first-link-empty-host.md](full-view-first-link-empty-host.md) | A full view's first attempt opens a link with an empty host (":80") and loses 10 s before the second works. Solved 2026-10-30 | 2026-10-29 |
| [opus-cost-on-the-10-1.md](opus-cost-on-the-10-1.md) | Opus encoding costs 11.8 ms per 20 ms packet on the Guition 10.1 beside four tiles, 7.8 on the D1001 | 2026-10-29 |
| [d1001-internal-ram-drop.md](d1001-internal-ram-drop.md) | The reTerminal D1001's internal RAM fell from 284 to 140 KB in 18 minutes with the encoder and sensing running | 2026-10-29 |
| [addon-counts-a-reboot-as-missing.md](addon-counts-a-reboot-as-missing.md) | The add-on's frame watch counts a screen's reboot (sequence numbers restart) as hundreds of thousands of missing frames | 2026-10-29 |
| [video-left-behind-at-half-buffer.md](video-left-behind-at-half-buffer.md) | A screen's video leaves a viewer behind until the next key frame once half its 64 KB send buffer is unacknowledged (lwIP's select), 9 to 36 times a minute over Wi-Fi | 2026-10-29 |
| [governor-slow-loop-feedback.md](governor-slow-loop-feedback.md) | A full view held up on the main loop raises the governor's step, which squeezes the tiles and sensing beside it | 2026-10-29 |
| [plugins-before-a-firmware-update.md](plugins-before-a-firmware-update.md) | A screen's Update builds with the plugins it has; a plugin that uses a form removed from the plugin API fails in the compiler, and only then is its update named | 2026-10-29 |
| [tile-refused-after-quick-views.md](tile-refused-after-quick-views.md) | After a full view opened and closed quickly a few times, the app refuses the S3's live tile (503) three times and it keeps its stills until the page turns | 2026-10-30 |
| [camera-sound-key-clipped.md](camera-sound-key-clipped.md) | The full view's sound key on a reTerminal D1001 showed only its bottom right quarter, once, in an opening whose stream came 5 s late | 2026-11-03 |
| [call-picture-over-the-whole-glass.md](call-picture-over-the-whole-glass.md) | A call's picture over the whole glass with its keys over it: 1.9 to 4.2 pictures a second, the minimum is 8 | 2026-11-10 |
| [doorbell-talk-delay.md](doorbell-talk-delay.md) | A doorbell's Talk reaches a Reolink about 3 s late, as Home Assistant's own talk button does | 2026-11-10 |
| [calls-before-release.md](calls-before-release.md) | What is left of calls before a release: flash on 4 MB boards, the ring's volume, ringing at night | 2026-11-10 |
