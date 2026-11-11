# A text as a tile

A Home Assistant text (`text`, and the helper `input_text`) is a tile that shows its value. On a board with 8 MB of
flash or more a tap opens the value in a field with the screen's keyboard (docs/KEYBOARD.md), and the check sends it to
Home Assistant. A board with 4 MB (the CYD first) shows the value only, on the tile and on its plain card, and the editor
says so on such a screen.

## What Home Assistant says

Both are text entities in Home Assistant (`InputText` is a `TextEntity`): the state is the value, any text
of at most 255 characters (`MAX_LENGTH_STATE_STATE`), an empty one included. Its attributes are `min` and `max` (the
fewest and the most characters, as Python's `len()` counts them, so `é` and `€` are one each), `pattern` (a regular
expression) and `mode` (`text` or `password`). An `input_text` defaults to 0 and 100, a `text` to 0 and 255.

The action is `text.set_value` or `input_text.set_value` with `value`. They do not behave the same:

- `text.set_value` refuses a value that is too short, too long or does not match `pattern`, with an error.
- `input_text.set_value` leaves the value as it was when it is too short or too long, with a warning in Home Assistant's
  log and no error, and does not check `pattern` at all.

Home Assistant's own row for a text (`hui-input-text-entity-row`) is a field with the value, `minlength` and
`maxlength`, the type `password` for a password, disabled while the entity is unavailable. It sends a value only when it
differs from the state, and never `unknown` or `unavailable`.

## The tile

- The value as it is: `on` is a text here, not On, and an empty value leaves the second line empty.
- One rule for a long value: a card of one row keeps one line under the name, ending in dots as every value line does;
  a card of two rows or more keeps its icon and name at the top and gives the value the body under them, over as many
  lines as it holds (at most eight), the last one ending in dots. A short value stands in the middle of the body, as any
  value does, and is not repeated under the name. A password stays one line of dots.
- A password shows a dot (•) for every character, on the tile, on its plain card, in its field and in the top bar.
- `unknown` (no value yet) and `unavailable` read as for every other entity.
- Its icon is Home Assistant's: `form-textbox` for both (the frontend's fallback for a type whose integration has no
  icon of its own), or one the entity or the tile chose.
- No controls and no other face: the tile is its value, and the tap is the field.

The screen keeps a text's whole value, up to 1020 bytes (255 characters of four bytes), where any other state is cut to
160 bytes, so a field never sends back a value cut short. A text in the top bar shows its value the same way.

## The field

A tap on the tile opens a page with the page's top bar (the back key, the entity's name and a check) and the keyboard at
the bottom. Between them stands a text area with the whole value over as many lines as it takes, as wide as the keys,
the cursor at its end. The keyboard comes without its own one-line field there (`Spec::field` off). A text of 255
characters reads whole on a 10.1 inch glass; on smaller glass the lines around the cursor stay in view.

- **The cursor goes where a finger puts it.** A finger on the text puts the cursor between the two characters nearest to
  it at once, and a finger held and dragged takes the cursor along, as on a phone. The keys type there and backspace
  erases before it.
- **The check saves.** The check in the top bar and the check at the keys' bottom right both send the value: a check
  needs no word in ten languages.
- **Glass too short for both** (the keys would take the whole glass, or leave no room for two lines of text): the
  keyboard takes the whole glass with its own one-line field, its close key and its send key, as the to-do card's does.
- **At most `max` characters.** The keyboard counts characters as Home Assistant does, not bytes, and a key that would
  pass `max` types nothing.
- **At least `min` characters.** With fewer the checks in the top bar and at the keys' bottom right are faded and send nothing,
  as Home Assistant's field refuses a value under its `minlength`.
- **`pattern` is Home Assistant's.** The screen does not rebuild a regular expression. A `text` refuses a value that
  does not match, and the tile shows the old value again; an `input_text` takes it, as it does in Home Assistant.
- **No suggestions**, and no hint in an empty field.
- **A password** shows a dot per character in the text area too, and the cursor moves between the dots.
- **Back changes nothing**: the page closes and Home Assistant hears nothing. So does the check on a value that is what
  Home Assistant has, or on `unknown` or `unavailable`.
- **What is sent** is the field as it stands, spaces included, as Home Assistant's field sends it. The keyboard types no
  space at the start of a text and no two spaces in a row; a value that has them keeps them.
- An unavailable text opens its plain card, which says so. A text with no value yet opens an empty field.
- A new value from Home Assistant while the field is open keeps what is typed, as Home Assistant's field does; a change
  of `min`, `max` or `mode`, or the entity going away, builds the page again.

The value goes out through `wish()` (docs/OPTIMISTIC.md, field `TEXT`): the tile shows it at once, the action goes out
at once, and Home Assistant squares it. A refused value (an error from `text.set_value`) puts the old value back at once;
a value `input_text` leaves unchanged comes back when Home Assistant reports the old value, or after the wish's cap when
it reports nothing.

## Which boards

The keyboard lives only where something uses it (docs/KEYBOARD.md, "What a board pays for it"). The field is the module
`text_edit` (docs/MODULES.md), so the boards with 8 MB of flash or more have it and a 4 MB board carries none of it:
the CYD's image has no symbol of `keyboard::` or `text_edit`.

What every board pays for the tile itself, measured on the CYD (`tools/check.sh --firmware --board cyd`, ESPHome
2026.9.0): 1,950,592 bytes before, 1,951,920 after, 1,328 bytes for the two types in the catalogue, the value over
several lines on a taller card, a password's dots, the dot (•) in the five text fonts and the `form-textbox` icon. Editing would add the field
and the keyboard: on a 10.1 inch P4 build their code is about 10.6 KB (`text_edit`) and 9.9 KB (`keyboard::`, shared
with the to-do card), some 20 KB a 4 MB board would carry anew, on a CYD at 96 % of its slot where only fixes ship. So a
4 MB board shows the value (wishlist 109) and edits nothing (wishlist 9).

A screen whose firmware is older than 0.61.0 does not know the types: the catalogue's `firmware: 0.61.0` is a hard
requirement, so the add-on asks for a firmware update before it sends such a layout (`catalogue.gates`,
`core.min_firmware`), as for every new type.

## The places a change touches

| Part | Files |
|---|---|
| What the tile shows | `tile_controls.h` (`text_entity`, `text_value`, `text_shown`), `runtime_tiles.h` (the value line, `detail_state`), `runtime_model.h` (`Tile::secret`, `available()` of an empty value), `page_receiver.cpp` (the state's length, `min`, `max`, `mode`) |
| The field | `module_text_edit.h` (the spec, what the check does, the text area: `wrap`, `plan_area`, `caret_at`), `module_text_edit.cpp` (the page), `module_text_edit_view.h` |
| The keyboard's arguments | `keyboard.h` (`Spec::chars`, `least`, `mask`, `field`, `Entry::at`, `place`, `caret`), `keyboard_lvgl.h`, docs/KEYBOARD.md |
| What the app sends | `core.py` (`TEXT_ATTRS`, `TEXT_STATE_BYTES`), `header_bar.py` (a password in the top bar), `tile_icons.py` (`FALLBACK_DOMAIN_ICONS`) |
| The editor | `model/tile-text.ts` (the value and its dots), `model/library.ts`, `model/layout.ts`, `TileInspector.vue` (the hint), `types.ts` and `server.py` (`text_edit`) |
| The catalogue | `catalogue/text.yaml`, `catalogue/input_text.yaml`, `catalogue/_ha.json` |

## Tests

- `tests/test_text_edit.cpp`: what the tile shows, the field's spec from Home Assistant's attributes, what the check
  does with too few or too many characters, the same value, a state's word and spaces, and the text area: lines that
  break after a word, the cursor's line in view, a finger that puts the cursor between two characters, a password's dots.
- `tests/test_keyboard.cpp` (`entity_field`): characters, not bytes, the faded check under `least`, and the dots of a
  masked field on six boards.
- `tests/test_layout_audit.py`: a long text and a password on every board shape.
- `tools/render/run.py --only text`: the real firmware on the host: tiles of every size with a short value, a long one,
  a password and an empty one, the text area of the long value, a finger that puts the cursor in it and a letter typed
  there, the password's field, the check faded under `min`, and a value typed and sent (`input_text.set_value`), in
  light and dark.
