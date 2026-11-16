# Host render checks that fail on dev: the swipe past excluded pages, and three stages

## The symptom

`tools/render/run.py jc8012p4a1` (the full stage list, the demo layout's page navigation round in `run.py`, about
line 747) stops with `AssertionError: swipe must stop before excluded pages` and reports the variant as FAIL. Every
stage after it in the same run is skipped; a stage run alone with `--only <stage>` is not affected.

Three more stages of the same run stop on their own checks, also on plain dev (2026-11-15, 19904265, jc8012p4a1, each
with `--only`):

- `automation`: `the screen never sent automation.toggle: ['automation.turn_off']`;
- `remote`: `the screen never sent remote.toggle: ['remote.turn_off']`;
- `bars`: `bars: group: no pager` and `bars: group-2: no pager`.

The cards of these stages are drawn before the check stops them.

## What we know

- 2026-11-15, on plain origin/dev 64db5812 (no local changes), jc8012p4a1, ESPHome 2026.9.0: the check fails after
  "swipe must stay within included pages" passed. So a second swipe from page 1 toward an excluded page left the home
  page, where the check expects it to stay.
- The check came in with f6c155f2 ("Implement page-owned layouts and stable page navigation"). When it started to fail
  is not known: no bisect was run.
- It is a host self test only; nothing is known about the glass. Swiping past an excluded page on a real screen has not
  been tried for this.

## Ruled out

- The card look work (docs/THEME.md "A card's look"): the failure is the same on origin/dev without it.

## Candidates

For automation and remote: the card's tap now sends turn_off where the harness expects toggle (the tap rule changed, or
the harness's expectation is older than it). For bars: the group card's pager moved or is drawn only on another condition.

- The swipe or page code changed what a swipe does at the last included page (a wrap, or a step onto an excluded page).
- The check's own setup (which pages it marks excluded, the swipe setting it switches on) no longer matches the layout
  it builds.

## The deciding experiment

For each stage alone, the same as for the swipe: `git bisect` between f6c155f2 and origin/dev with `python3 tools/render/run.py jc8012p4a1` as the test (about four
minutes a step), then read the first commit that fails against `swipe_pages` and the page navigation in
`runtime_tiles.h`.

## Pointers

`tools/render/run.py` (the navigation round, `swipe()`), `settings_screen::swipe_pages`, `go_to_page` and the page
navigation in `components/smart_display/runtime_tiles.h`, docs/PAGES.md "The address" and "Navigation".

## Solved: the swipe (2026-11-16)

The check was older than the rule, and the firmware was right. Loop pages (2afbe908, 2026-11-10, on by default) says
that past the last page comes the first, skipping the excluded pages (`PageData::step`), and that is what the screen
did: on the guition host build, a swipe from the last included page went to the first included page (page 0), never
to an excluded one. 0239533f makes the round state the rule both ways: with Loop pages on, the swipe comes round to
the first page; with the "Loop pages" switch off, it stops at the last included page. The guition host render passes
whole (51 page checks). The automation, remote and bars stages above are still open.

## Solved: automation, remote and bars (2026-11-16)

Automation and remote were the checks', not the firmware's. A tap on a switching tile sends what Home Assistant's own
toggle sends, `turn_on` or `turn_off` by the state the tile shows and never `toggle` (`optimistic_lvgl.h`,
`toggle_tap`); automation and remote follow that rule since 0.4.38, and the checks still waited for `toggle` from
0.4.11. They now wait for `turn_off` and `turn_on`, and the check that holding a tile switches nothing looks for all
three. Bars passes on dev's tip as it is. Both whole renders pass: guition and jc8012p4a1, 55 page checks each.
