"""The keyboard layout a screen is built with (docs/KEYBOARD.md, "The layout of a screen").

A screen built in German types on QWERTZ, every other one on QWERTY. The language is the LANGUAGE substitution that
ESP Screens writes into a screen's YAML (`smart_display: language:`), so there is no setting of its own and nothing is
chosen while the screen runs. The build defines SCREEN_KEYBOARD_QWERTZ, keyboard::standard() (keyboard.h) takes that
table, and the firmware holds the one layout its language types on. keyboard::layout_for() makes the same choice for
the browser preview, which carries every language; tests/test_keyboard_layout.py keeps the two lists equal.
"""

# The languages that do not type on QWERTY, by their first subtag (de, de-AT and de-CH alike), and their layout.
LAYOUTS = {'de': 'qwertz'}
# The define that puts a layout in a screen's firmware in place of QWERTY.
DEFINES = {'qwertz': 'SCREEN_KEYBOARD_QWERTZ'}


def layout(language):
    """The layout a screen built in `language` types on."""
    return LAYOUTS.get((language or '').split('-')[0], 'qwerty')


def defines(language):
    """The defines a screen built in `language` needs for its keyboard: none for QWERTY."""
    define = DEFINES.get(layout(language))
    return [define] if define else []
