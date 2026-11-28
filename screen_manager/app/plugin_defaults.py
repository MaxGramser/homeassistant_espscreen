"""Plugins the app suggests for a board (docs/PLUGINS.md, "Plugins a board starts with").

A board can have hardware that only does something with a plugin: a camera without Screen camera is a lens nobody
reads. RULES says which plugin goes with which hardware, and why. The app never adds one by itself; it suggests, and a
person answers once:

- New screen: a step of the wizard lists what this board's rules suggest, ticked, each with its reason. What stays
  ticked is built into the screen's first firmware; what is unticked is not suggested for that screen again.
- A screen that is there already: a card above it suggests the plugin. Yes brings it with the screen's next update, or
  builds it now when no update waits; no is kept, and the card never comes back for that plugin on that screen.

A rule names a plugin of the app's own index (never a link or a folder: a plugin cannot suggest itself), the feature
of the board that calls for it (boards.json `features`, from the board's files), the first version worth suggesting,
and the key of its reason (`editor.plugins.suggest.why.<why>` in the translations). A new rule is one line here and
one sentence there; plugins.py, the wizard and the card read this table and know no plugin by name.
"""

# plugin: the id in the index; feature: what the board must have; since: the first version suggested; why: the reason.
RULES = (
    # Screen camera costs a screen that never uses its camera next to nothing since 0.7.0 (docs/CAMERA.md).
    {'plugin': 'screen_camera', 'feature': 'camera_sensor', 'since': (0, 7, 0), 'why': 'camera'},
)


def rules_for(features):
    """The rules a board with these features meets, in the table's order."""
    have = set(features or ())
    return [rule for rule in RULES if rule['feature'] in have]


def suggested_ids():
    return {rule['plugin'] for rule in RULES}
