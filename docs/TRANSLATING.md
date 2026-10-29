# Translating Tessera

Tessera speaks every language it has a file for: the screens, the editor in Home Assistant and the messages of the
app. Each language is one JSON file in [`screen_manager/translations/`](../screen_manager/translations/). English
(`en.json`) is the source. Every other file has the same keys. A language goes in with every text translated
(`tools/i18n.py check` asks for that), most of them drafted and marked `"checked": false` until someone who speaks the
language went through them. A text added later shows in English until its translation follows.

You can help in two ways, and neither needs you to write code:

- **Check a language** that is already there. Most were drafted by Claude and need someone who speaks the language.
- **Add a language** that isn't there yet.

## Where the texts show

| Section | Where you see it | Keep in mind |
| --- | --- | --- |
| `screen` | On the screens themselves | Screens are small, especially the CYD. Keep it as short as the English. A screen gets new texts with its next firmware update. |
| `addon` | Messages of the app, and texts it sends to the screens (tile names, the top bar) | Error messages are whole sentences. |
| `editor` | The Tessera editor in Home Assistant | Shows up as soon as the app is updated. |
| `_meta` | The language itself | See [The `_meta` block](#the-_meta-block). |

Three parts fill themselves. Don't change them by hand:

- `screen.ha` holds Home Assistant's own words for states: on and off, open and closed, heating, the weather.
  `tools/i18n.py ha-words` copies them from Home Assistant's translations, so a screen says exactly what the Home
  Assistant app says. To improve one of these words, change it in
  [Home Assistant's translations](https://developers.home-assistant.io/docs/translations/); we pick it up from there.
- `screen.date` holds day and month names and the order of a date. `screen.number` says how numbers are written.
  `screen.time.am` and `.pm` are the day periods. All of this comes from the Unicode CLDR, the same data every browser
  uses, through `tools/i18n.py cldr`. One list is yours: `screen.date.weekdays_min`, the days of the weather card in
  two letters (`di`, `lu`, `ma` in French), because the small screen has room for no more. `cldr` starts a new language
  with a guess and then leaves the list alone. `screen.number.percent` follows Home Assistant's own rule: a space before `%` in
  Czech, German, Finnish, French, Slovak and Swedish, none in the other languages.
- `_meta.clock`, 12 or 24 hours, also comes from the CLDR.

How the clock and numbers are written doesn't wait for a translation: `screen_manager/app/regions.json` holds them for
every language Home Assistant offers, also from the CLDR. A Swedish Home Assistant gets English texts on the screens until
there is a `sv.json`, but already the Swedish 24-hour clock and `1 234,5`.

## Check a language

1. Open the file of your language, for example
   [`nl.json`](../screen_manager/translations/nl.json), next to [`en.json`](../screen_manager/translations/en.json).
   `_meta.checked` says whether someone checked it already.
2. Read it through. Look for three things:
   - wrong words;
   - words that differ from the ones the Home Assistant app uses in your language (the Home Assistant app is the
     reference: *Dashboard*, *Automation*, *Entity* are what people know);
   - texts that are too long for a small screen. `tools/i18n.py check` measures the line under a tile's name with the
     screens' own font (a `{time}` in it as a 12-hour clock, the widest a screen writes) and says when it doesn't fit;
     for the rest, compare with the English. `screen.script.yesterday_time_short` is that line's short wording, which
     a tile falls back to when `yesterday_time` doesn't fit there: keep both the same where your word is short enough.
3. Look at it for real, if you can. In Tessera open **Settings → Language & region** and choose your language. The
   editor itself follows the language of your Home Assistant profile. The screens show the new texts after their
   firmware update.
4. Change what needs changing. To find a word you saw, search for it in the file: the key it sits under says where it
   shows (`screen`, `addon`, `editor`), and the same key in `en.json` holds the English. A word under `screen.ha` is
   Home Assistant's own: change it in [Home Assistant's translations](https://developers.home-assistant.io/docs/translations/)
   instead, or the next `tools/i18n.py ha-words` puts Home Assistant's word back. When the whole file is checked, set
   `"checked": true` in `_meta`.
5. Send it in (see [Sending your work](#sending-your-work)). Say in the pull request which parts you checked.

A partial check helps too. Say which sections you went through, and leave `checked` at `false`.

## Add a language

1. Pick the code Home Assistant uses for your language (`sv`, `da`, `cs`, `pt-BR`); Tessera follows Home Assistant's
   language setting by that code. A variant such as `pt-BR` may be a small file with only the texts that differ from
   `pt`. That is how `en-GB` works: it holds the 24-hour clock and British spelling, and the rest falls back to `en`.
2. Create the file. If you have Node.js and Python:

   ```bash
   python3 tools/i18n.py new sv Svenska Swedish one_other
   ```

   This writes `sv.json` with its `_meta` and the calendar from the CLDR. The last word is the plural rule (see
   [Plurals](#plurals)). Without these tools, copy `en.json`, keep only `_meta` and the texts you translate, and a
   maintainer adds the calendar.
3. Translate. Keep the keys and the structure of `en.json`. Translate the text values only. Start with `screen`, which
   is short and what people see every day, then `editor` and `addon`.
4. Check it:

   ```bash
   python3 tools/i18n.py check
   ```

5. Send it in. A maintainer fills `screen.ha` from Home Assistant (`tools/i18n.py ha-words`).

### Which languages fit

| Script | Languages | Screens |
| --- | --- | --- |
| Latin | English, Dutch, German, French, Italian, Spanish, Portuguese, Polish, Czech, the Nordic languages, Turkish, ... | Every screen: the fonts carry every letter European languages use |
| Cyrillic | Russian | Yes: the Cyrillic letters go only onto a screen built in a Cyrillic language (see "Letters" below) |
| Cyrillic, Greek | Ukrainian, Bulgarian, Greek | Possible in the same way: a maintainer adds the language to the list, or a list for a new script. Ask first. |
| Chinese, Japanese, Korean | | Only on a Guition, with the characters the texts need; a CYD has too little room and shows English |
| Right-to-left, or letters that join | Arabic, Hebrew, Persian, Thai, Hindi | Not yet: the screens' graphics library doesn't write them without extra work |

The editor and the app's messages work in any language, whatever the screens can draw.

### Letters

The five text fonts of every screen carry the Latin letters European languages use, and nothing more, because flash is
tight on every board. A language written in another script brings its letters along only where they are needed:

- Its translation file names the script in `_meta.script` (`cyrillic`).
- `packages/core.yaml` has one list of letters per script (`SCRIPT_GLYPHS_CYRILLIC`) and picks it with `SCRIPT_GLYPHS` by
  the screen's `LANGUAGE`, which the app writes into the screen's own YAML. The text fonts end on `"${SCRIPT_GLYPHS}"`,
  so a screen built in Russian carries the Cyrillic letters and every other screen carries none of them.
- The app keeps those letters in what it sends to that screen alone: names and state words in Cyrillic reach a Russian
  screen, and other screens get them left out as before (`header_bar.SCRIPT_GLYPHS`, `clean_text`).
- `tools/i18n.py check` accepts the letters of a language's own script in its screen texts. A test keeps the lists in the
  firmware and the app equal, and the languages `SCRIPT_GLYPHS` takes equal to the files that name that script.

A list holds the letters its languages write and no more, since every letter is drawn in five fonts on every screen
built in that language. To add a language of a script that has a list, add its code to `SCRIPT_GLYPHS` beside `ru` and
the letters it writes that the list lacks to both lists (Ukrainian adds Є, є, І, і, Ї, ї, Ґ and ґ). A new script takes a
list of its own in both places, letters the text font (Roboto) has.

## The format

- **Placeholders** such as `{n}`, `{name}` or `{time}` stay exactly as they are. Move them to where your sentence needs
  them: `"Last {time}"` can become `"Zuletzt {time}"` or `"{time} geleden"`.
- **Plurals** are the forms of one sentence, separated by ` | `, in the order of your language's rule:
  `"1 hour ago | {n} hours ago"`.
- **Brand names stay:** Tessera, Home Assistant, ESPHome, Claude, Guition, CYD.
- **Keep the characters `{ } | @` out of ordinary text:** the editor reads them as instructions.
- **Match the tone:** short and plain, like the English. The screens and the editor talk to people at home, not to
  engineers.

### Plurals

| Rule | Languages | Forms |
| --- | --- | --- |
| `one_other` | English, Dutch, German, Italian, Spanish, Portuguese (Portugal), the Nordic languages | one \| other: `1 hour ago \| {n} hours ago` |
| `one_upto_1` | French, Brazilian Portuguese | the first form for 0 and 1 |
| `slavic_pl` | Polish | one \| few (2-4, 22-24, ...) \| many |
| `east_slavic` | Russian, Ukrainian | one \| few \| many |
| `none` | Chinese, Japanese, Korean | one form |

### The `_meta` block

| Field | Meaning |
| --- | --- |
| `name` | The language in itself: `Nederlands`, `Deutsch` |
| `english` | The language in English |
| `script` | `latin`, `cyrillic`, `greek`, `han`, ... |
| `plural` | One of the plural rules above |
| `clock` | `12` or `24`: what *Automatic* means for the clock (from the CLDR) |
| `checked` | `true` once someone who speaks the language has checked the whole file |

## Sending your work

- **On GitHub, without Git:** open the file on GitHub and press the pencil. GitHub makes a copy and a pull request for
  you.
- **With Git:** fork the repository, change the file, run `python3 tools/i18n.py check`, open a pull request.
- **No GitHub account?** Open an issue or mail the file. We'll take it from there.

Translations ship with the next release of Tessera: the editor and messages right away, the screens with their next
firmware update.

## For maintainers

- **A new English text:**
  - Screen texts: add the key to `en.json` and run `python3 tools/i18n.py header`. That writes
    `components/smart_display/screen_text_keys.h`, which the build checks against the JSON. The code uses
    `screen_text::tr(txt::...)`. A number with a unit goes through `screen_text::with_unit`, a percentage through
    `screen_text::percent`, so the spacing is Home Assistant's.
  - App texts: use `i18n.t(...)` for the editor's language, and `i18n.screen_t(...)` for the screens' language.
  - A text that is stored or made outside a request uses `i18n.english(...)`. That covers a delivery status and an
    update result. `i18n.shown(...)` puts it in the language of the editor that asks. Numbers and times for the
    screens go through `i18n.screen_number(...)` and `i18n.screen_clock(...)`, units through `i18n.unit_suffix(...)`.
  - A screen gets the app's words in the language its firmware speaks (its "Screen language" sensor), so a screen that
    isn't updated yet stays in one language; firmware from before the languages gets English and its own letters.
    `Manager.sync_one` sets that screen for the texts it writes (`i18n.SCREEN`).
  - Editor texts: go through vue-i18n.
- **Every release:** Claude drafts the new texts for every language, with Home Assistant's own words as the glossary,
  and leaves them unchecked for a speaker of the language. A missing text falls back to English at runtime,
  but the release check refuses missing keys in a full language. Regional variants may inherit from their base language.
- **Before a release:**
  - `python3 tools/i18n.py check`: keys, placeholders, plurals, letters the screens can't draw, long screen texts.
  - `python3 tools/i18n.py lint`: English left in the firmware's code. What stays English on purpose is listed in
    `LINT_KEEP`, with the reason.
  - `python3 tools/i18n.py header --check`.
- **Refreshing the words from Home Assistant and the calendar:**

  ```bash
  python3 tools/i18n.py ha-words --write
  python3 tools/i18n.py cldr --write
  ```

  `ha-words` needs a Home Assistant: `HA_URL` and `HA_TOKEN` in the environment. When Home Assistant adds a language,
  add its code to `HA_LANGUAGES` in `tools/i18n.py` and run `cldr --write` for its clock and numbers.
- **What stays English everywhere:**
  - the names of the screens' own entities in Home Assistant (renaming one gives it a new entity id). The add-on
    also finds a screen by the names of its diagnostic entities (`NAME_*` in `screen_manager/app/core.py`: Tile
    settings, Screen firmware, Device name, Screen board, ...). If one must change, keep the old name in its
    `NAME_*` pair, and for Tile settings `Manager.follow_renamed_inboxes` as well, since the stored layouts are
    keyed by its entity id. A new unit or device class for an existing sensor needs a new entity, because Home
    Assistant's registry keeps the old one;
  - log lines;
  - the statuses the app reads from a screen;
  - release notes;
  - the Claude skill.
