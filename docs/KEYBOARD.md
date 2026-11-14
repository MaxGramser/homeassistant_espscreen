# The keyboard

The screen's own keyboard: a sheet at the bottom of the glass with a field, the key that sends it, a row of
suggestions and four rows of keys. The to-do card is its first user (docs/TODO.md, "The keyboard") and a Home Assistant
text's field the second (docs/TEXT_ENTITY.md); any other part of the UI that needs a text (a search field, a rename, a
plugin's card) uses the same one, with its own hint, suggestions, send key and limits.

It is in two parts, as the touch feedback is (docs/PLUGINS.md, "Touch feedback"):

| Part | File | What it knows |
|---|---|---|
| The plan | `components/smart_display/keyboard.h` | Layouts, what a key does to what is typed (`Entry`), and the sheet as rectangles, texts and places a finger may hit (calendar_card.h `Scene`). No LVGL, no Home Assistant, no caller. |
| The glass | `components/smart_display/keyboard_lvgl.h` | One LVGL object (`keyboard::lvgl::Sheet`) that paints the plan, hears the finger and tells its caller what happened. |

## What it does

- A sheet at the bottom of the glass, never wider than 16.5 cm, with keys of at most 9 mm. On glass too short to keep
  the caller's page above it, it takes the whole glass, so its keys stay at least 6.5 mm high, and it gets a close key
  in front of the field.
- Three pages: letters, digits (`123`) and signs (`#+=`). The first letter is a capital.
- Holding a letter shows its accents in a strip above it (é è ê ë for e); a tap takes one. Holding backspace keeps
  erasing.
- A tap on a key darkens it at once, and a key repaints only the keyboard's own sheet, never the caller's page.
- The field shows the end of a long text, and the hint while it is empty.

## The spec

What a caller asks for is one `keyboard::Spec`:

| Field | What it is | Default |
|---|---|---|
| `layout` | The keys (see "A new layout"); `keyboard::layout("qwerty")` finds one by name. | QWERTY |
| `hint` | The words in the empty field. | none |
| `suggestions` | Texts in a row above the keys. A tap on one is the caller's. | none |
| `keep_row` | The row of suggestions keeps its room while it has none to show, so the keys never move under a finger while the suggestions follow what is typed. | no |
| `send_glyph` | The send key as an icon of the screens' icon font. | the check |
| `send_word` | The send key as a word ("Search", "Save"), in place of the icon; the key grows to fit it and the field gives way. | none |
| `most` | The most bytes the field holds; a character that does not fit whole is left out. | 120 |
| `chars` | The most characters the field holds, counted as Home Assistant counts a text (Python's `len()`: code points, so `é` and `€` are one each); a key that would pass it types nothing. 0 for no limit beyond `most`. | 0 |
| `least` | The fewest characters the send key takes. With fewer, the send key and the check key at the bottom right are faded, take no shade under a finger and send nothing, as Home Assistant's field refuses a text under its `minlength`. | 0 |
| `mask` | The field shows a dot (•, `keyboard::MASK`) for every character instead of the text: a password. | no |
| `field` | The field and its send key above the keys. Off, the sheet is the keys alone, lower by the field's row, and the check at the bottom right sends: for a caller that shows the text itself (a text entity's text area). Without the field there is no close key either, so such a caller keeps the field where the sheet would take the whole glass. | yes |

What is typed is a `keyboard::Entry` the caller keeps: its text, the page, shift, and the letter whose accents show.
`keyboard::reset(entry, text)` starts it, with a text to change (a rename, a text entity's value) or empty: what is
typed goes at its end, where the cursor stands, and a start value begins with small letters. `keyboard::typed(entry)`
is the text without spaces at either end; a caller that sends a text as it stands reads `entry.text` instead (a text
entity's field does). `entry.at` is the cursor, a byte offset where keys type and before which backspace erases;
`reset` puts it at the end, `keyboard::place(entry, at)` where a caller's finger put it (on the start of a character),
and `keyboard::caret(entry)` reads it back inside the text. The field draws the cursor where it stands. `keyboard::characters(text)` counts characters as `chars` and `least` do, and
`keyboard::sendable(entry, spec)` says whether the send key takes what the field holds.

## Using it

The pure part plans the sheet for a test or for the caller's own plan:

```cpp
keyboard::Spec k;
k.hint = "Search";
k.send_word = "Search";
keyboard::Entry entry;
keyboard::reset(entry);
calendar_card::Scene scene;
const keyboard::Place where = keyboard::plan(scene, measure, W, H, top, entry, k);
// where.top: the sheet begins there; where.whole: it took the whole glass
```

On the glass a caller keeps one `keyboard::lvgl::Sheet` per page, sets its callbacks once, and calls `show()` each time
its page is laid out while the keyboard is up, and `hide()` when it goes:

```cpp
static keyboard::lvgl::Sheet keys;
keys.on.changed = [](const std::string &text) { keys.spec().suggestions = matches(text); };
keys.on.send = [](const std::string &text) { search(text); keys.hide(); };
keys.on.suggestion = [](size_t, const std::string &text) { search(text); keys.hide(); };
keys.on.hidden = [] { keys.hide(); };
const keyboard::Place where = keys.show(page, measure, faces, W, H, top, entry, spec);
// the page keeps what lies above where.top (or nothing, when where.whole)
```

- `allow(kind)` is asked before a tap acts, with the kind of place it hit (`KEY`, `SEND`, `SUGGESTION`, `HIDE`,
  `PANEL`): the caller's guard against a bounce (the to-do card guards all but the letters, as before), or a check that
  its page is still there.
- `changed(text)` comes after every key, before the sheet is planned again: the place to set new suggestions.
- `send(text)` comes from the send key and from the check key at the bottom right, never while the field holds fewer
  than `least` characters. The keyboard stays up: the caller resets the entry for the next text (the to-do card does)
  or hides it (a text entity's field closes its page).
- `suggestion(index, text)` and `hidden()` are the caller's too.
- `moved()` comes when a key moved where the sheet begins (suggestions that came or went without `keep_row`): the
  caller lays its page out again and calls `show()`. Without it the sheet moves by itself.
- When the page that holds the sheet goes, `forget()`; a page that is cleaned with its sheet in it is noticed by the
  sheet too.

The sheet's object covers the sheet alone, so the caller's page above it keeps its own touches, and it paints with the
fonts (`faces`) and the `measure` the caller hands it, the same the caller plans with.

The keyboard's places in a `Scene` are its own kinds of `calendar_card::Hit` (69 to 73). A caller that also puts the
keyboard into a scene of its own, as the to-do card's plan does for its tests, keeps its own kinds off them.

## A new layout

A layout is a table in `keyboard.h`, like `qwerty()`:

- the letters and the capitals, a page of digits and a page of signs, each with the same number of keys;
- three rows of letters, at most 10, 10 and 7 keys (the third row stands between shift and backspace, the first two on
  a grid of ten, a shorter row in its middle);
- the accents of a letter, at most six, in lower and upper case;
- the labels of the keys that change the page (`123`, `#+=`, `abc`).

Add the table and a line in `keyboard::layout()`, and the planner, the sheet and every caller take it as it is.
`tests/test_keyboard.cpp` keeps a layout of its own (AZERTY, 10, 10 and 6 keys) to prove that no more is needed.

What it costs:

- **A Latin layout** (AZERTY, QWERTZ, a Nordic or a Polish one) costs a few hundred bytes of tables, and only on a
  screen whose firmware uses the keyboard. Its letters are already in the fonts.
- **Another script** (Greek, Cyrillic, Hebrew) needs its letters in the five text fonts of `packages/core.yaml`, at
  every size of every board, which costs flash on every screen, the 4 MB ones first (docs/TRANSLATING.md and
  `SCRIPT_GLYPHS` already do this for a screen built in such a language). `tests/test_keyboard_glyphs.py` fails until
  every character of every layout is in those fonts, and every icon the keyboard draws is in the fixed icon set.

There is no choice of layout on the screen yet: a caller names the one it wants.

## What a board pays for it

Both files are headers, and nothing of them is made unless a caller uses them. Every header of this component lands
in the firmware's `main.cpp`, where the keyboard stays unused on a board without a caller; the to-do card uses it from
`module_todo.cpp` and `module_text_edit.cpp`, which only boards with the `todo` and `text_edit` modules compile
(docs/MODULES.md). So a board without a user of the
keyboard carries none of it, without a define of its own: the CYD's image has no symbol of `keyboard::`.

A new caller in a module of its own adds it to the boards of that module. A caller in the shared code adds it to every
board, the 4 MB ones too: measure the CYD with `tools/check.sh --firmware --board cyd` before and after, and look for
`keyboard::` in its symbols. A change in a header the CYD only includes can move its size by a few kilobytes either way as the linker packs
the same code differently; a symbol of the keyboard in its image is what says it pays.

## Tests

- `tests/test_keyboard.cpp`: the keyboard alone, on the faces of six boards: what a key types and the limit of the
  field, every place inside the glass and every key a finger can hit, a second layout, a send key that is a word or a
  caller's icon, the row of suggestions with and without its room, the accents of a letter, the whole glass.
- `tests/test_keyboard_glyphs.py`: every character of every layout is in the screens' fonts.
- `tests/test_keyboard.cpp` (`entity_field`): characters and not bytes, the faded send key under `least`, a start
  value, the cursor (typing and erasing in the middle, never two spaces side by side), the dots of a masked field and
  the keys without their field, on six boards.
- `tests/test_todo.cpp`: the keyboard as the to-do card uses it.
- `tests/test_text_edit.cpp`: the keyboard as a text entity's field uses it.
- `tools/render/run.py --only todo`: the real firmware typing on the host (the to-do card's keyboard, its accents and
  its names offered); `--only text` a text entity's field, a password's, the faded check and a value sent.

## The places a change touches

| Part | Files |
|---|---|
| A key, a page or the sheet | `keyboard.h`, `tests/test_keyboard.cpp`, this document; the key positions `tools/render/run.py` works out for the to-do card (`todo_panel`, `keys`) |
| A layout | `keyboard.h` (its table and `layout()`), `tests/test_keyboard_glyphs.py` runs on it; for another script, `packages/core.yaml` (the text fonts' glyphs) |
| The finger, the shade of a key, the callbacks | `keyboard_lvgl.h`, its callers (`module_todo.cpp`), this document |
| A new caller | its own module or file, docs/KEYBOARD.md's list of callers below, and the CYD's size if it is shared code |

Callers today: the to-do card (`module_todo.h` `typing_spec`, `module_todo.cpp`) and a text entity's field
(`module_text_edit.h` `spec`, `module_text_edit.cpp`), both modules of the full tier.
