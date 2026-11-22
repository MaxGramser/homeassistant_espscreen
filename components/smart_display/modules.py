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

# name: the lowest tier that has it, the define its code is gated by, and whether the editor's firmware preview
# (web/wasm, docs/EMULATOR_ARCHITECTURE.md) is built with it. The preview is this firmware compiled for the browser: it
# takes every module that draws from what the add-on sends, and leaves out the ones that need a part it has none of (a
# finger's edge swipe, live pictures, a microphone). web/wasm/build.py and generate_renderer_manifest.py read this
# column; until 2026-11-15 they named three modules by hand, so the preview drew no sections while the app said it did.
MODULES = {
    # Up from the bottom edge opens a window of every page to pick from; lite goes home as before.
    "dock": {"min_tier": "full", "define": "SD_MOD_DOCK", "preview": False},
    # The vacuum card with its map, its rooms and its routines; lite keeps the card it had.
    "vacuum_card": {"min_tier": "full", "define": "SD_MOD_VACUUM_CARD", "preview": False},
    # A cover group's page, a card per cover, behind a key on its card; lite keeps the cover card alone.
    "cover_groups": {"min_tier": "full", "define": "SD_MOD_COVER_GROUPS", "preview": False},
    # The screensaver's clock faces beside the digital clock: Glass, Classic and Bauhaus; lite keeps the digital clock.
    "clock_faces": {"min_tier": "full", "define": "SD_MOD_CLOCK_FACES", "preview": False},
    # A doorbell's ring opens its camera live with a chime, on a screen that streams (a P4); lite shows alerts only.
    "doorbell": {"min_tier": "full", "define": "SD_MOD_DOORBELL", "preview": False},
    # Calls between screens (docs/CALLS.md): needs a microphone, a speaker and live pictures, which only a P4 has together.
    "call": {"min_tier": "full", "define": "SD_MOD_CALL", "preview": False},
    # The template tile: a text Home Assistant renders from a template, as rows the app sends; lite is not offered it.
    "text_card": {"min_tier": "full", "define": "SD_MOD_TEXT_CARD", "preview": True},
    # A light's presets: round keys on its tile and its card that set a colour and a brightness; lite draws the slider.
    "light_presets": {"min_tier": "full", "define": "SD_MOD_LIGHT_PRESETS", "preview": True},
    # The to-do card: a list to tick, its full screen and the keyboard that adds an item; lite has no to-do tile.
    "todo": {"min_tier": "full", "define": "SD_MOD_TODO", "preview": True},
    # A text's field: a Home Assistant text or input_text edited with the keyboard; lite shows the value only.
    "text_edit": {"min_tier": "full", "define": "SD_MOD_TEXT_EDIT", "preview": True},
    # Sections on a page (docs/PAGES.md "Sections"): blocks of cells with a title, an icon and a panel; lite gets the
    # same tiles in the same cells, without the sections.
    "sections": {"min_tier": "full", "define": "SD_MOD_SECTIONS", "preview": True},
}


def preview_modules():
    """The names of the modules the editor's firmware preview is built with, in the table's order."""
    return [name for name, m in MODULES.items() if m["preview"]]


def tier_for_flash(flash_mb):
    """The tier of a board with `flash_mb` MB of flash; None (a host build) is full."""
    return "full" if flash_mb is None or flash_mb >= FULL_FLASH_MB else "lite"


def modules_for(tier):
    """The names of the modules a screen of `tier` gets, in the table's order."""
    rank = TIERS.index(tier)
    return [name for name, m in MODULES.items() if TIERS.index(m["min_tier"]) <= rank]
