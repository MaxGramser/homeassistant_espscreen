# Testing a change to the screens

A test counts when it walks the path the product walks and looks at the moment a bug would live in. A function called
directly, or a screen looked at once it has settled, can pass while the screen on the wall shows the bug for a second
after every page change (GitHub #27 was exactly that). So before calling a change tested, say which entry point was
driven (a finger, a layout message from the add-on, an action from Home Assistant) and which moment was looked at.

There are four levels, from fast to real.

## 1. The fast checks

`tools/check.sh`: the Python tests of the add-on and the tools, every C++ test of the firmware's logic, the package
check, the generated files (cells, board shapes, entry files, icons), the translations and the editor's tests, types
and build. `tools/check.sh --firmware` compiles every board as its owners build it, with the flash budget of the CYD.
`--affected` (or `--board <key>`) compiles only the boards a change reaches, which for a fix in one board file is one
build instead of all of them; docs/BOARD_RELEASES.md says which boards a change reaches and why.

## 2. Every board on this computer

`tools/render/run.py` (and `tools/check.sh --render`, and CI's render job) builds the real firmware of every board in
`boards.yaml` as a program for this computer: the same C++ and LVGL as on the glass, with an SDL window in place of the
panel and the touch chip. Lying down, and standing up where the glass is not square. For each it:

- sends the demo layout through the screen's inbox, as the add-on does, with a title per page;
- runs the firmware's own self test (`ui_self_test`): every page and overlay, each page's cards and bar, and the check
  that nothing falls outside its area. A FAIL fails the run;
- changes page with a finger: from the edge of the glass across the tiles and back, through ESPHome's own touchscreen
  (its transform, the touch guard, the edge swipe or LVGL's gesture), read at the rate the board reads its touch panel;
- reads back, every 50 ms from the moment the finger lifts, the page title as its label shows it: a title that stands
  in dots for a moment and then whole is a failure;
- shows three alerts and one with a camera picture, and reads the card back as it opens, before the picture, and right
  after the picture arrives: every part inside the card, nothing over anything else;
- saves every page, the alerts and Dark mode as pictures, with a sheet of all boards. CI compares them with the commit
  before and keeps the pictures and a before/after/difference picture of every one that changed.

What it cannot show: colours and timing of a real panel, a real finger on real glass, memory and heat, and anything a
real Home Assistant or camera adds.

## 3. One screen on the glass

`diagnostics/send_layout.py` pushes the same demo layout to a screen over its API; `diagnostics/run_ui_test.py` runs its
self test; `diagnostics/capture_ui.py` saves what LVGL draws on a Guition as a picture. A new board is flashed and
walked through by hand: touch in the corners, a drag, the backlight, the colour order, a page swipe from each edge, and
the same standing up (docs/ADDING_A_BOARD.md).

## 4. The whole chain

The release a user gets, from end to end, on a screen of its own (not one a household depends on):

1. Update ESP Screen Manager in Home Assistant to the release.
2. Add the screen with **New screen**. With the board on the Home Assistant machine, flash it there; otherwise choose
   **Download** and flash the file from your own computer.
3. Pair it: Home Assistant finds the screen, and with ESPHome Device Builder installed it takes the key from the
   screen's YAML by itself.
4. Give it tiles in ESP Screens, with real entities, and look at the glass.
5. Send an alert the way an automation does, `esp_screens_show_alert` with a `camera`: every screen gets the picture at
   the size of its own frame, and older firmware its old frame. It goes to every screen, so choose a moment for it.
6. Swipe, tap the alert's button, open a camera. Leave tiles that switch real things alone unless that is the test.

docs/TEST_RESULTS_*.md says, per release, which of these were done and what they showed.
