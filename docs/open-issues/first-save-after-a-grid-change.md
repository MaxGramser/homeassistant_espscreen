# The first save after a grid change: refused until the screen was saved once

## The symptom

A screen whose layout was never saved yet: its grid is changed in the editor (Screen settings, the grid picker) and
Save says "This change of grid could not be saved" (before 2026-11-24 "Screen grid changed; explicit layout adaptation
is required"). Trying again never helps. Saving once on the grid the screen has and then changing the grid works
(GitHub #355, a Tab5 on 0.4.92 and 0.4.98).

## What we know

- `screen_manager/app/page_service.py` `save_pages`: a save with an `adaptation` is refused when nothing is stored
  (`not previous`), because the expected `from` is the stored layout's `sourceGrid`, which a screen without a saved
  layout has none of. The editor's `from` (web/src/stores/document.ts) is the screen's default grid (`source_grid`,
  `record_grid(inbox, None)` in server.py), so it can never match.
- The check came with f6c155f2 (2026-09-24), when a grid changed only when a screen reported another one, which needs a
  stored layout. The grid picker (35116f9a, app 0.4.85) made a grid change before the first save possible. No test
  covers it: every API test starts from a stored layout (tests/test_page_api.py `asyncSetUp`).
- A save that loses to another window's save also gets this message, because the adaptation is checked before the
  revision (`layout_store.py`).
- On 2026-11-24 the maintainer chose to change only the message (it says what to do, every language); the fix below is
  not built.

## The fix not chosen (yet)

- In `save_pages`, when nothing is stored, take the screen's own grid (`record_grid(inbox, None)`, kept before
  `chosen` replaces it) as the expected `from`, and refuse only a stored layout in the old `legacy-v1` format instead of
  `not previous`. `to` stays checked by `chosen_grid`; every other guard stays. About four lines, with an API test:
  no stored layout, the screen's grids known, `{from: default, to: 2x4}` gives 200 and a wrong `from` 400.
- Check the revision before the adaptation in `save_pages`, so a stale draft gets the layout-conflict message.

## Pointers

`screen_manager/app/page_service.py` (`save_pages`), `screen_manager/app/layout_store.py` (`save`),
`screen_manager/app/server.py` (`chosen_grid`, `takes_grid`, `record_grid`, `verified_grid`),
`web/src/stores/document.ts` (the adaptation a save sends).
