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
| [blue-flash-p4.md](blue-flash-p4.md) | A whole frame of light blue, one frame, on the reTerminal D1001 and sometimes the Guition 10.1 under memory-bus load; the panel never reports an underrun | 2026-10-25 |
| [addon-webrtc-loss-on-yellow.md](addon-webrtc-loss-on-yellow.md) | On a Home Assistant Yellow the add-on loses WebRTC packets of the biggest stream when a full view runs: the asyncio loop near one core | 2026-10-29 |
| [full-view-first-link-empty-host.md](full-view-first-link-empty-host.md) | A full view's first attempt opens a link with an empty host (":80") and loses 10 s before the second works. Solved 2026-10-30 | 2026-10-29 |
| [opus-cost-on-the-10-1.md](opus-cost-on-the-10-1.md) | Opus encoding costs 11.8 ms per 20 ms packet on the Guition 10.1 beside four tiles, 7.8 on the D1001 | 2026-10-29 |
| [d1001-internal-ram-drop.md](d1001-internal-ram-drop.md) | The reTerminal D1001's internal RAM fell from 284 to 140 KB in 18 minutes with the encoder and sensing running | 2026-10-29 |
| [addon-counts-a-reboot-as-missing.md](addon-counts-a-reboot-as-missing.md) | The add-on's frame watch counts a screen's reboot (sequence numbers restart) as hundreds of thousands of missing frames | 2026-10-29 |
| [video-left-behind-at-half-buffer.md](video-left-behind-at-half-buffer.md) | A screen's video leaves a viewer behind until the next key frame once half its 64 KB send buffer is unacknowledged (lwIP's select), 9 to 36 times a minute over Wi-Fi | 2026-10-29 |
| [governor-slow-loop-feedback.md](governor-slow-loop-feedback.md) | A full view held up on the main loop raises the governor's step, which squeezes the tiles and sensing beside it | 2026-10-29 |
| [plugins-before-a-firmware-update.md](plugins-before-a-firmware-update.md) | A screen's Update builds with the plugins it has; a plugin that uses a form removed from the plugin API fails in the compiler, and only then is its update named | 2026-10-29 |
| [tile-refused-after-quick-views.md](tile-refused-after-quick-views.md) | After a full view opened and closed quickly a few times, the app refuses the S3's live tile (503) three times and it keeps its stills until the page turns | 2026-10-30 |
