"""The tiers and the modules of the firmware (docs/MODULES.md).

A screen's tier follows from its flash, never from a board's name or its look: a board with less than 8 MB is `lite`
(the CYD and every other 4 MB board, close to their update slot), every other board is `full`. A host build has no
flash and says the one it stands in for (`smart_display: flash_mb:`, tools/render/host.py).
A module is a piece of the UI that only a tier has room for. It lives in module_<name>.h beside the shared code
(ESPHome copies a component's own folder, not folders inside it), is reached from the shared code only inside `#ifdef`
of its define, and so a lite screen never compiles a byte of it.

tools/generate_board_shapes.py reads this table for boards.json (what the add-on and the editor know a board has), and
tests/test_modules.py checks that no module code is reached without its define.
"""

TIERS = ("lite", "full")
# Below this the board is lite.
FULL_FLASH_MB = 8

# name: the lowest tier that has it, and the define its code is gated by.
MODULES = {
    # Up from the bottom edge opens a window of every page to pick from; lite goes home as before.
    "dock": {"min_tier": "full", "define": "SD_MOD_DOCK"},
    # The vacuum card with its map, its rooms and its routines; lite keeps the card it had.
    "vacuum_card": {"min_tier": "full", "define": "SD_MOD_VACUUM_CARD"},
    # A cover group's page, a card per cover, behind a key on its card; lite keeps the cover card alone.
    "cover_groups": {"min_tier": "full", "define": "SD_MOD_COVER_GROUPS"},
    # The screensaver's clock faces beside the digital clock: Glass, Classic and Bauhaus; lite keeps the digital clock.
    "clock_faces": {"min_tier": "full", "define": "SD_MOD_CLOCK_FACES"},
}


def tier_for_flash(flash_mb):
    """The tier of a board with `flash_mb` MB of flash; None (a host build) is full."""
    return "full" if flash_mb is None or flash_mb >= FULL_FLASH_MB else "lite"


def modules_for(tier):
    """The names of the modules a screen of `tier` gets, in the table's order."""
    rank = TIERS.index(tier)
    return [name for name, m in MODULES.items() if TIERS.index(m["min_tier"]) <= rank]
