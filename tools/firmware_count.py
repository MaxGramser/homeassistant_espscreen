"""How firmware numbers count (app 0.3.21, docs/BOARD_RELEASES.md "Core and board in one number"): the one place the
tools and the release checks read that rule from.

A firmware number is X.Y.Z. Y is the core: a shared release, one every board builds, is the next X.Y.0. Z is a board's
revision on that core: a fix for one board alone keeps the core and raises Z in that board file only. A feature gate
names a shared X.Y.0, so a board at X.Y.2 passes the gates of its core and no newer one.

Up to LAST_OLD_COUNT the last number counted the core (0.3.0 to 0.3.10 were all shared releases); the count above
takes over from there. The add-on's own core.firmware_target only takes the higher of the shared number and a board's,
which needs none of this, and the add-on's image carries no tools/.

Standard library only.
"""
import re

LAST_OLD_COUNT = (0, 3, 10)
NUMBER = re.compile(r'(\d+)\.(\d+)\.(\d+)')


def parse(text):
    """(X, Y, Z) of a strict "X.Y.Z" (quotes around it allowed, as YAML writes it); None for anything else."""
    match = NUMBER.fullmatch(str(text).strip().strip('"')) if text is not None else None
    return tuple(int(part) for part in match.groups()) if match else None


def dotted(number):
    return '.'.join(map(str, number))


def next_shared(core):
    """The number of the next shared release after the shared `core`: the core goes up and the revision starts at 0."""
    return (core[0], core[1] + 1, 0)


def next_board(core, built):
    """The number of a fix for some boards alone on the shared `core`, where `built` are the numbers those boards build
    now: the same core, a revision above every one of them (several boards share one number)."""
    return (core[0], core[1], max([core[2], *(number[2] for number in built if number and number[:2] == core[:2])]) + 1)


def board_problem(core, board):
    """What is wrong with a board's own number `board` on the shared `core`, or None: it keeps the core's X.Y (the core
    it is built on) and has a revision above the core's."""
    if board[:2] != core[:2]:
        return 'another core'
    if board[2] <= core[2]:
        return 'no board revision'
    return None


def shared_problem(previous, number, highest):
    """What is wrong with a new shared number after the shared `previous`, where `highest` is the highest number any
    release took so far, or None. Above LAST_OLD_COUNT it raises the core and ends in .0; below it, it only had to rise."""
    if highest is not None and number <= highest:
        return 'not above'
    if number > LAST_OLD_COUNT and (number[2] != 0 or (previous and number[:2] <= previous[:2])):
        return 'no new core'
    return None
