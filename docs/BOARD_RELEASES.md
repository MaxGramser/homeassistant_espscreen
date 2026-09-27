# Releases per board

Tessera runs on many boards. Most changes reach all of them, but a new board or a fix for one board should not make
every screen in every home rebuild its firmware. Since app 0.3.20 a board can have a firmware version of its own, so
only the screens that actually get something new are offered an update.

This page is the recipe. It says which kind of release a change is, what to change, which checks to run, and why the
rules are what they are. docs/RELEASING.md has the general release steps; this page is the part that depends on which
boards a change reaches.

## Start here: which boards does the change reach?

```bash
tools/affected_boards.py
```

It compares your working tree (commits, staged and unstaged changes, new files) with where your branch left
`origin/main`, sorts every changed path, and prints the release that follows: the version to set, the CHANGELOG heading
to write, and the checks to run. `--base <ref>` compares with something else, and `--keys` prints only the board keys
(that is what `tools/check.sh --affected` uses).

How a path is sorted:

| Changed path | Reaches |
|---|---|
| `packages/core.yaml`, anything under `components/` or `fonts/` | every board |
| the `screen` section of a file in `screen_manager/translations/` (the texts the firmware compiles in) | every board |
| a board file under `packages/boards/`, or its entry files `packages/<board>.yaml` and `checkout/<board>.yaml` | that board |
| a file under `packages/features/`, `looks/`, `hardware/` or `cells/` | exactly the boards whose files include it |
| anything else: the add-on, the editor, docs, tests, tools, `boards.yaml`, the other translation texts | no firmware |

A board whose board file is not on `origin/main` yet is **new**. No screen runs it, so it never counts toward a
firmware release.

The four outcomes are the four recipes below.

## How the version numbers work

There are two version numbers, and they do different jobs.

- **The app version** (`version:` in `screen_manager/config.yaml`) is what Home Assistant offers as an add-on update.
  Every push to main is a release, so every push bumps it, with a CHANGELOG entry.
- **The firmware version** is what a screen reports in its **Screen firmware** sensor. The add-on compares it with the
  version the screen's board builds today, and offers **Update** when the screen is behind.

The firmware version is set in two places:

- `SCREEN_FIRMWARE_VERSION` in `packages/core.yaml` is the **shared** version. `FIRMWARE_VERSION` in
  `screen_manager/app/core.py` holds the same number.
- A board file may set its own `SCREEN_FIRMWARE_VERSION` under `BOARD_ID`. A board file's substitution wins over the
  core's (docs/PROFILES.md, "Which value wins"), so that board builds and reports its own number. It must be higher than
  the shared one.

`tools/generate_board_shapes.py` writes each board's version into `screen_manager/app/boards.json` (`firmware`).
The add-on offers a screen the higher of the shared version and its board's version (`core.firmware_target`). It takes
the board from the screen's own ESPHome YAML, because that is what an update builds, and falls back to the board the
screen reports.

### One rising series of numbers

All firmware numbers, shared and per board, form a single series. **The next firmware number is always one above the
highest number in the CHANGELOG**, whichever kind of release it is. `tools/affected_boards.py` prints it.

This rule matters because the add-on uses the firmware number for two things: the update offer, and the feature
gates. A feature gate says "this screen can draw a tall tile from firmware 0.2.xx". Suppose a board fix took 0.3.10 and
the next shared release took 0.3.10 as well:

- screens of that board would already report 0.3.10 and never be offered the shared release;
- and the add-on would believe they have every feature of shared 0.3.10, which they don't.

With one rising series, a board fix is 0.3.10, the next shared release is 0.3.11, and both problems are impossible.
For the same reason a feature gate only ever names a shared version: a board-only release never brings a new feature
the add-on has to know about.

When a shared release overtakes a board that went ahead, that board's own line goes: the shared release contains its
fix too (the fix is in its board file, which the shared release builds). `tools/check_packages.py` fails as long as a
board file states a version that is not above the shared one.

### What screens see

- A screen of a board that went ahead is offered its board's version; every other screen stays up to date.
- **What's new** under Update lists the CHANGELOG entries between the screen's firmware and its target, and leaves out
  entries for other boards (`## 0.3.20 (firmware 0.3.10 for waveshare4b)` only shows on that board).
- The nightly update round only picks up screens that have an update, so a board fix flashes only those screens.

### Older apps and newer firmware

The Screen firmware sensor still reports a plain `X.Y.Z`, the only form every app version reads. An older app
compares with its own `FIRMWARE_VERSION`, so a screen on a newer board fix just reads as up to date there.

## A new board

A new board is not a firmware release. It has no screens yet, and it builds the shared firmware from main like every
other board.

1. Follow docs/ADDING_A_BOARD.md for the board itself.
2. Don't set `SCREEN_FIRMWARE_VERSION` in its board file, and don't change the shared version.
3. Run `tools/affected_boards.py`. It should say "New board: <key>" and "No firmware change for a screen that exists".
   If it also names an existing board, you touched a shared file or another board's file on the way: that part is its
   own release (one of the recipes below), and it may be better as a separate change.
4. Bump `screen_manager/config.yaml` and write a CHANGELOG entry that names the shared firmware:
   `## 0.3.21 (firmware 0.3.10)`.
5. Checks:

   ```bash
   tools/check.sh
   ```

   ```bash
   tools/check.sh --firmware --board <key>
   ```

   ```bash
   tools/render/run.py <key>
   ```

   Render `<key>-portrait` as well when the glass is not square. The other boards need no build: nothing they use
   changed.

## A fix for one board (or a few)

The change only touches files that `tools/affected_boards.py` sorts under that board: its board file, a feature file
only it includes, its entry files.

1. Make the fix in the board's own files. If the fix needs `packages/core.yaml` or a component, it is a shared fix,
   even when only one board shows the bug.
2. Run `tools/affected_boards.py`. It prints the next firmware number, say 0.3.11.
3. In the board file, under `BOARD_ID`:

   ```yaml
   substitutions:
     BOARD_ID: "waveshare4b"
     SCREEN_FIRMWARE_VERSION: "0.3.11"   # a fix for this board alone (docs/BOARD_RELEASES.md)
   ```

   If the board already has a line from an earlier fix, raise it to the new number.
4. Leave `packages/core.yaml` and `FIRMWARE_VERSION` alone.
5. Run `tools/generate_board_shapes.py` (it writes the version into boards.json).
6. Bump `screen_manager/config.yaml` and write the CHANGELOG entry with the board key:

   ```markdown
   ## 0.3.22 (firmware 0.3.11 for waveshare4b)
   ```

   Several boards: `(firmware 0.3.11 for waveshare4b, guition)`, each board file set to 0.3.11. Use the keys of
   `boards.yaml`. Say in the entry that other screens get nothing new.
7. Checks:

   ```bash
   tools/check.sh
   ```

   ```bash
   tools/check.sh --firmware --affected
   ```

   `--affected` builds only the boards the change reaches (the same as `--board waveshare4b`). The CYD flash budget
   only runs when the CYD is one of them. Render the board with `tools/render/run.py <key>`, and test it on the glass
   when the fix is about something only hardware shows.

## A shared fix or feature

Anything in `packages/core.yaml`, `components/`, `fonts/` or the screen texts, or a package every board includes.

1. Run `tools/affected_boards.py`. It prints the next number, say 0.3.12, and lists the boards that went ahead.
2. Set `SCREEN_FIRMWARE_VERSION` in `packages/core.yaml` and `FIRMWARE_VERSION` in `screen_manager/app/core.py` to it.
3. Remove `SCREEN_FIRMWARE_VERSION` from every board file that went ahead: the new shared version is higher and
   includes their fixes. `tools/check_packages.py` fails until you do.
4. A new feature the add-on has to know about gets a gate on this shared number (docs/RELEASING.md).
5. `tools/generate_board_shapes.py`, bump `screen_manager/config.yaml`, CHANGELOG entry `## 0.3.23 (firmware 0.3.12)`.
6. Checks:

   ```bash
   tools/check.sh --all
   ```

   ```bash
   tools/check.sh --render
   ```

   Every board compiles and the CYD flash budget applies (docs/RELEASING.md step 2).

## The app alone

The add-on, the editor, docs or tools changed, and no firmware.

1. Bump `screen_manager/config.yaml` and write a CHANGELOG entry that names the shared firmware again:
   `## 0.3.24 (firmware 0.3.12)`. That is fine while a board is ahead of it.
2. Check with `tools/check.sh`. No firmware build: no screen gets anything new.

A change to the README or docs alone can go to main without a release (docs/RELEASING.md).

## What the checks hold

These run in `tools/check.sh` and CI, so a release that breaks a rule fails before it is pushed.

| Check | Holds |
|---|---|
| `tools/check_packages.py` | only the core and a board file set `SCREEN_FIRMWARE_VERSION`; a board's own version is `X.Y.Z` and above the shared one |
| `tools/generate_board_shapes.py --check` | `boards.json` carries each board's version as its files work it out |
| `tests/test_release_lint.py` | the numbers in the CHANGELOG are one rising series and never used twice; the newest entry names what it ships; a board that went ahead has its entry; board keys in headings exist |
| `tests/test_board_releases.py` | what `tools/affected_boards.py` sorts where, the plan it prints, and that a board file's version wins over the core's |
| `tests/test_updates.py` | a board fix is offered to that board alone, an update waits for the board's version, and the target is never below the shared one |
| `web/tests/store.spec.ts` | What's new goes by the screen's own target and leaves out other boards' entries |

The precedence the whole scheme rests on (a board file's substitution over the core's) was checked with a real
`esphome config` when this was built: a board file with its own version built and reported that version in its project
version, its Screen firmware sensor and its settings page, and the CYD next to it kept the shared one.

## Mistakes to avoid

- **Reusing a number.** Never give a shared release a number that a board fix already used, and never give a board fix
  a number that is already out. Take the one `tools/affected_boards.py` prints.
- **A feature gate on a board-only number.** A gate compares with shared versions only.
- **A "board fix" in a shared file.** A change to the core or a component reaches every board, whatever it was meant for.
  Then it is a shared release.
- **Forgetting to raise the version.** A fix in a board file without a new number reaches new screens (they build
  from main) but is never offered to the screens that already run that board.
- **Leaving a board's line behind after a shared release.** The check fails; remove the line.
- **Setting the version in a feature or look file.** Only a board file may, so each board's number is in one obvious
  place.
