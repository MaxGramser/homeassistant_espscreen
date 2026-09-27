# Releases per board

Tessera runs on many boards. Most changes reach all of them, but a new board or a fix for one board should not make
every screen in every home rebuild its firmware. Since app 0.3.21 a board can have a firmware version of its own, so
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

A YAML file that changed in its comments or layout alone reaches no board: the tool compares what ESPHome reads of
it (its YAML tokens), so a better explanation in a board file is no update. The lines of a lambda are text to YAML,
so a changed `#ifdef` inside one does count.

A board whose board file is not on `origin/main` yet is **new**. No screen runs it, so it never counts toward a
firmware release.

**The ESPHome version** the add-on builds with (`screen_manager/Dockerfile`) counts as no firmware either, on purpose.
A newer ESPHome changes every build, but it brings nothing a screen owner asked for, so it is no reason to ask every
screen to update: screens pick it up at their next real update. A release that needs a newer ESPHome for a firmware
change is a firmware release because of that change.

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
  core's (docs/PROFILES.md, "Which value wins"), so that board builds and reports its own number.

`tools/generate_board_shapes.py` writes each board's version into `screen_manager/app/boards.json` (`firmware`).
The add-on offers a screen the higher of the shared version and its board's version (`core.firmware_target`). It takes
the board from the screen's own ESPHome YAML, because that is what an update builds, and falls back to the board the
screen reports.

### Core and board in one number

A firmware number `X.Y.Z` reads as core and board (from the shared firmware 0.4.0 on):

- **Y is the core.** Every shared release raises it and starts the last number at 0: 0.4.0, 0.5.0, 0.6.0.
- **Z is the board's revision on that core.** A fix for one board alone keeps the core and raises the last number
  for that board only: 0.4.1, then 0.4.2. The other boards stay at 0.4.0. Two boards can both be at 0.4.1, each with
  its own fix.
- **X** stays 0.

| Release | Core | Waveshare 4B | CYD and the others |
|---|---|---|---|
| shared release | 0.4.0 | 0.4.0 | 0.4.0 |
| fix for the 4B | 0.4.0 | 0.4.1 | 0.4.0 |
| another fix for the 4B | 0.4.0 | 0.4.2 | 0.4.0 |
| next shared release (has the 4B fixes too) | 0.5.0 | 0.5.0 | 0.5.0 |

`tools/affected_boards.py` works the next number out from `origin/main` and prints it. The rule itself lives in one
place, `tools/firmware_count.py`, which the package check, the plan and the release lint all read.

The number has to stay three plain numbers: every app version and Home Assistant read a screen's firmware as strict
`X.Y.Z`, and anything else would read as no firmware at all.

This reading matters because the add-on uses the firmware number for two things: the update offer, and the feature
gates. A feature gate says "this screen can draw a tall tile from firmware 0.2.xx". A feature belongs to the core, so
from 0.4.0 on a gate always names a shared X.Y.0. A 4B on 0.4.2 passes a gate on 0.4.0 and stays below one on 0.5.0,
which is exactly what it has: core 4 with fixes of its own. A board revision never brings a feature the add-on has to
know about.

When a shared release raises the core, a board that went ahead drops its own line: the shared release contains its
fix too (the fix is in its board file, which the shared release builds). `tools/check_packages.py` fails as long as a
board file names another core than the shared one, or no revision above it.

Up to firmware 0.3.10 the last number counted the core (0.3.0 to 0.3.10 were all shared releases). The next shared
release is 0.4.0 and the count above holds from there; `tools/firmware_count.py` knows 0.3.10 as the last number of the
old count. A fix for one board before that release keeps shared 0.3.10 as its core: 0.3.11 for that board.

### What screens see

- A screen of a board that went ahead is offered its board's version; every other screen stays up to date.
- **What's new** under Update lists the CHANGELOG entries between the screen's firmware and its target, and leaves out
  entries for other boards (`## 0.3.21 (firmware 0.4.1 for waveshare4b)` only shows on that board).
- The Settings page names one firmware only when the screens share it, and otherwise says how many screens can update.
- The nightly update round only picks up screens that have an update, so a board fix flashes only those screens.

### Older apps and newer firmware

The Screen firmware sensor still reports a plain `X.Y.Z`, the only form every app version reads. An older app
compares with its own `FIRMWARE_VERSION`, so a screen on a newer board fix just reads as up to date there.

## A new board

A new board is not a firmware release. It has no screens yet, and it builds the shared firmware from main like every
other board.

1. Follow docs/ADDING_A_BOARD.md for the board itself, and run `tools/generate_issue_templates.py` so the board
   dropdown of the GitHub issue forms lists it (tools/check.sh fails until you do).
2. Don't set `SCREEN_FIRMWARE_VERSION` in its board file, and don't change the shared version.
3. Run `tools/affected_boards.py`. It should say "New board: <key>" and "No firmware change for a screen that exists".
   If it also names an existing board, you touched a shared file or another board's file on the way: that part is its
   own release (one of the recipes below), and it may be better as a separate change.
4. Bump `screen_manager/config.yaml` and write a CHANGELOG entry that names the shared firmware:
   `## 0.3.21 (firmware 0.4.0)`.
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
2. Run `tools/affected_boards.py`. It prints the next firmware number, say 0.4.1 on core 0.4.0.
3. In the board file, under `BOARD_ID`:

   ```yaml
   substitutions:
     BOARD_ID: "waveshare4b"
     SCREEN_FIRMWARE_VERSION: "0.4.1"   # a fix for this board alone (docs/BOARD_RELEASES.md)
   ```

   If the board already has a line from an earlier fix, raise it to the new number.
4. Leave `packages/core.yaml` and `FIRMWARE_VERSION` alone.
5. Run `tools/generate_board_shapes.py` (it writes the version into boards.json).
6. Bump `screen_manager/config.yaml` and write the CHANGELOG entry with the board key:

   ```markdown
   ## 0.3.22 (firmware 0.4.1 for waveshare4b)
   ```

   Several boards: `(firmware 0.4.1 for waveshare4b, guition)`, each board file set to 0.4.1 (above what each of them builds now). Use the keys of
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

1. Run `tools/affected_boards.py`. It prints the next number, say 0.5.0, and lists the boards that went ahead.
2. Set `SCREEN_FIRMWARE_VERSION` in `packages/core.yaml` and `FIRMWARE_VERSION` in `screen_manager/app/core.py` to it.
3. Remove `SCREEN_FIRMWARE_VERSION` from every board file that went ahead: the new shared version is higher and
   includes their fixes. `tools/check_packages.py` fails until you do.
4. A new feature the add-on has to know about gets a gate on this shared number (docs/RELEASING.md).
5. `tools/generate_board_shapes.py`, bump `screen_manager/config.yaml`, CHANGELOG entry `## 0.3.23 (firmware 0.5.0)`.
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
   `## 0.3.24 (firmware 0.5.0)`. That is fine while a board is ahead of it.
2. Check with `tools/check.sh`. No firmware build: no screen gets anything new.

A change to the README or docs alone can go to main without a release (docs/RELEASING.md).

## What the checks hold

These run in `tools/check.sh` and CI, so a release that breaks a rule fails before it is pushed.

| Check | Holds |
|---|---|
| "Firmware numbers for what changed" (`tools/affected_boards.py --verify`) | every existing board a change reaches builds a higher number than on `origin/main`. While you work it warns; once `screen_manager/config.yaml` names a new app version (a release) it fails. CI checks it against the commit before the push, or the pull request's base, and always fails (`CHECK_BASE`) |
| `tools/check_packages.py` | only the core and a board file set `SCREEN_FIRMWARE_VERSION`; a board's own version is `X.Y.Z` on the shared core with a higher revision |
| `tools/generate_board_shapes.py --check` | `boards.json` carries each board's version as its files work it out |
| `tests/test_release_lint.py` | a shared firmware raises the core and ends in .0, a board fix is a revision on the shared core above its last one; the newest entry names what it ships; a board that went ahead has its entry; board keys in headings exist |
| `tests/test_board_releases.py` | the count of `tools/firmware_count.py`, what `tools/affected_boards.py` sorts where (comments alone included), the plan it prints, when `--verify` warns or fails, and that a board file's version wins over the core's |
| `tests/test_updates.py` | a board fix is offered to that board alone, an update waits for the board's version, and the target is never below the shared one |
| `web/tests/store.spec.ts`, `web/tests/components.spec.ts` | What's new goes by the screen's own target and leaves out other boards' entries; the Settings page names one firmware only when the screens share it |

The precedence the whole scheme rests on (a board file's substitution over the core's) was checked with a real
`esphome config` when this was built: a board file with its own version built and reported that version in its project
version, its Screen firmware sensor and its settings page, and the CYD next to it kept the shared one.

## What CI builds

The firmware job of CI builds only the boards that can have changed (`tools/affected_boards.py --build-keys`). A push
compares with the last commit on main where the same build (same ESPHome) succeeded, so the commits of a run that was
cancelled or failed are built by the next one; a pull request compares with its base. It builds every board every
night, when started by hand, and when there is no such commit. `--build-keys` differs from `--keys` in one way: a
change to what makes a build (the add-on's ESPHome, tools/check.sh, tools/profiles.py, boards.yaml, checkout/, the
override fixtures, the CI workflow, the selector itself) builds every board, although no screen needs an update for it.

| Push | CI builds |
|---|---|
| the app alone | no firmware |
| the build tooling (check.sh, profiles.py, boards.yaml, the CI workflow) | every board |
| a fix in one board file | that board, with both ESPHome versions |
| a change to the core or a component | every board |
| a new ESPHome in the add-on | every board |
| every night, or by hand | every board |

## Mistakes to avoid

- **A shared release that does not raise the core.** 0.4.3 after 0.4.0 reads as a board revision and is no update
  for a board already at 0.4.3. A shared release is always the next X.Y.0; take the one `tools/affected_boards.py`
  prints.
- **A board fix on the wrong core.** A board revision keeps the shared core: on core 0.4.0 it is 0.4.1, never 0.5.1.
- **A feature gate on a board revision.** A gate names a shared X.Y.0 only.
- **A "board fix" in a shared file.** A change to the core or a component reaches every board, whatever it was meant for.
  Then it is a shared release.
- **Forgetting to raise the version.** A fix in a board file without a new number reaches new screens (they build
  from main) but is never offered to the screens that already run that board, and a later update of another board
  takes it along unannounced. `tools/check.sh` warns while you work and fails at the release and in CI.
- **Leaving a board's line behind after a shared release.** The check fails; remove the line.
- **Setting the version in a feature or look file.** Only a board file may, so each board's number is in one obvious
  place.
