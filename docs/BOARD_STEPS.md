# A board's own steps

Most boards need nothing but their firmware. A few need one more thing done to them, once: a second chip that takes a
firmware of its own, a part someone sets by hand. A **step** is that one more thing. New screen offers it as a page of
its own after the screen works, and the screen's page offers it until it is done.

The first step is the SenseCAP Indicator's: Tessera's firmware for the RP2040 that drives its buzzer
(docs/SECOND_CHIP.md).

## What a person sees

- **New screen.** After the last page of the installation (the screen is in Home Assistant and may act), each step of
  the board that is not done gets a page: what it is and why, the key that does it, and **Later** under it. Later goes
  on to the last page and is kept, so nothing asks again by itself.
- **Above the screen.** A screen with a step that is not done, and that nobody put off, shows a card with the step's
  title and **Set it up**, which opens the same page in a window. **Not now** is kept as Later.
- **The screen's menu.** Every step of the board is in the menu, with what the screen found of it (a firmware version)
  or "not done". That is where a step that was put off waits, and where one that is done can be done again.
- **Newer.** When the app has something newer than what a screen found (a newer firmware for the chip), the card comes
  back as an update of that step.

## How a step is made of parts

| Part | Where | What it holds |
|---|---|---|
| The list | `boards.yaml`, `steps` in the board's entry | each step's `id`, its `kind`, and what the kind needs |
| The kind, in the app | `KINDS` in `screen_manager/app/board_steps.py` | the check of a step, what the editor gets to do it with, whether a screen can see it done, and when what it found is old |
| The kind, in the editor | `web/src/components/steps/kinds.ts` | the component that does the step |
| The words | `editor.steps.<id>` in the translations | `menu`, `title`, `lead`, `note`, `done_title`, `done_lead`, `update_title`, `update_lead` |
| The proof | the board file's `HELLO_BOARD_STEPS` | what the screen says in its hello: `steps: {id: what it found}` |

A step is **done** when the screen says so, for a kind the screen can see (`seen` in `KINDS`): its hello and every
answer to a ping carry `steps`, and the app reads it each time (`page_delivery.steps_of`), so a chip that got its
firmware a moment ago counts without a restart of anything. The page of a step asks the screen at once
(`POST api/screens/<id>/steps`). A kind the screen cannot see is done when the person says so, which the app keeps
(`board_steps.json`), as it keeps Later.

A screen whose firmware says nothing of steps (it was built before its board had any) is not offered a step only the
screen can call done: nobody could tell when it is. After its next update it says `steps`, empty, and the card comes.

## The kinds

### `chip_firmware`

Tessera's firmware for a second chip of the board, written from the browser through the chip's own USB port. The step
names the chip (`chip: indicator-rp2040`, its folder under `chips/`), and the app has the built file and what is known
of it in `screen_manager/app/chips/` (docs/SECOND_CHIP.md, "Building it").

It takes two clicks, because a browser hands a port and a folder only to a click:

1. **Write the firmware.** The page asks for the chip's serial port (the browser's list shows only ports with the
   chip's USB ids) and opens it at 1200 baud, which restarts the chip as a USB drive.
2. **Choose the drive.** The page asks for that drive, checks that it is the chip's (its `INFO_UF2.TXT` names the board)
   and writes the file to it. The chip starts with the new firmware, the screen finds it, and the page says so.
   **Play a sound** then lets the chip play its own two notes.

Where the browser has no USB port or no folder access (another browser than Chrome or Edge, a phone, a page over plain
http), the page gives the same file to download and the three steps by hand, and waits for the screen to find the chip.

## Adding a step

**Of a kind that exists**: the entry in `boards.yaml`, its words under `editor.steps.<id>` in every translation, the
board file's `HELLO_BOARD_STEPS` when the screen can see it done, and `tools/generate_board_shapes.py`. For a
`chip_firmware` step also the chip's firmware (docs/SECOND_CHIP.md).

**A new kind**:

1. A row in `KINDS` (`board_steps.py`): `view(step)` checks the step and returns what the editor needs, and raises
   `ValueError` with what is wrong, which stops `tools/generate_board_shapes.py`; `seen` and `stale` as above.
2. A component in `web/src/components/steps/`, in `kinds.ts`. It gets `step` and `screen`, does the step, and emits
   `done`. Its words go under `editor.steps.kinds.<kind>`.
3. Its section above, and a test in `tests/test_board_steps.py` and `web/tests/board-steps.spec.ts`.

A question that has to be answered before the firmware is built (which panel, which variant) is not a step: that is a
`choices` entry of the board, which New screen asks on its Model page.

## Tests

`tests/test_board_steps.py` (the checks, the states, what is kept, the catalog), `web/tests/board-steps.spec.ts` (the
card, the page, the kind `chip_firmware` from its first click to the screen that found the chip, and the way by hand).
