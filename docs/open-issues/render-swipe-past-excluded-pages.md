# The host render's navigation check fails: "swipe must stop before excluded pages"

## The symptom

`tools/render/run.py jc8012p4a1` (the full stage list, the demo layout's page navigation round in `run.py`, about
line 747) stops with `AssertionError: swipe must stop before excluded pages` and reports the variant as FAIL. Every
stage after it in the same run is skipped; a stage run alone with `--only <stage>` is not affected.

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

- The swipe or page code changed what a swipe does at the last included page (a wrap, or a step onto an excluded page).
- The check's own setup (which pages it marks excluded, the swipe setting it switches on) no longer matches the layout
  it builds.

## The deciding experiment

`git bisect` between f6c155f2 and origin/dev with `python3 tools/render/run.py jc8012p4a1` as the test (about four
minutes a step), then read the first commit that fails against `swipe_pages` and the page navigation in
`runtime_tiles.h`.

## Pointers

`tools/render/run.py` (the navigation round, `swipe()`), `settings_screen::swipe_pages`, `go_to_page` and the page
navigation in `components/smart_display/runtime_tiles.h`, docs/PAGES.md "The address" and "Navigation".
