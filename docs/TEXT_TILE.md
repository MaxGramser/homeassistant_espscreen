# The template tile

A tile without an entity: a text with Home Assistant templates in it, as in **Developer tools › Template**. Home
Assistant fills it in, the screen shows the result, and the screen follows every change of what the template reads. A
template that comes out empty makes the tile disappear, so a page can stay quiet until something needs you (wish #88:
"Conditional tiles, and a free-form content block").

![Template tiles on a 7-inch screen in light and dark mode, and on a 4-inch screen
screen](images/text_tile.png)

It is part of the module `text_card` (docs/MODULES.md): every board with 8 MB of flash or more has it. The CYD, the CYD
ILI9342 and the Hosyond 4-inch (4 MB) do not, and their firmware does not change by a byte.

## Writing a template

Add **Template** from the screen's own cards in the library, pick the tile, and write in its **Template** field. Two things
mix in it: Home Assistant's template language for what changes, and a little markup for how it looks.

### What changes: Home Assistant's templates

Everything between `{{ }}` and `{% %}` is Home Assistant's own Jinja, exactly as in Developer tools › Template and in
automations. Home Assistant's [template docs](https://www.home-assistant.io/docs/configuration/templating/) are the
reference. The ones a tile uses most:

| You write | You get |
|---|---|
| `{{ states('sensor.living_room_temperature') }}` | the state: `21.4` |
| `{{ states('sensor.power') \| float(0) \| round(1) }}` | a number with one decimal |
| `{{ state_attr('climate.living_room', 'current_temperature') }}` | an attribute |
| `{{ state_translated('lock.front_door') }}` | the state in your language: `Locked` |
| `{% if is_state('binary_sensor.dishwasher_done', 'on') %} … {% endif %}` | a part that shows only while true |
| `{% for light in states.light \| selectattr('state', 'eq', 'on') %} - {{ light.name }} {% endfor %}` | a line per light that is on |
| `{{ relative_time(states.sensor.washer.last_changed) }}` | `12 minutes` |
| `{{ now().strftime('%H:%M') }}` | the time |

The field helps while you type:

- After `states('`, `is_state('` or `state_attr('` it lists your entities, with their name and their state now.
- After `state_attr('climate.living_room', '` it lists that entity's real attributes, with their values.
- After `is_state('lock.front_door', '` or `states('…') == '` it lists the states that entity can have: the one it has
  now first, then what Home Assistant lists for it (a select's options, a thermostat's modes), then its domain's.
- `states.` lists the domains, `states.light.` your lights, `states.light.desk.` what a state has (`state`, `name`,
  `attributes`, `last_changed`).
- After `|` it lists the filters, after `{%` the tags (`if`, `for`, `set`), and inside the braces the functions.
- A function, a tag or a table comes as a snippet: its fields (the entity, the state, the condition, the cells) are
  selected one after the other with **Tab**, and a function that takes an entity opens the entity list at once.
- Beside the code stands what the template reads now: the value after a `states(…)` or `state_attr(…)`, and a ✓ after
  an `is_state(…)` that holds (or ✗ with the state it has).
- An entity id Home Assistant does not have is underlined, with a key that puts in the one it most likely meant. When
  Home Assistant names a line in its error, that line is marked too.
- Pointing at an entity id shows its name and state.
- **Ctrl+Space** shows what fits where the cursor is, at any moment, and **Ctrl+/** (⌘/ on a Mac) comments a line out
  as `{# … #}`, the comment Home Assistant reads.
- Under the result, **Updates when** names what makes Home Assistant render it again: the entities and domains it reads
  and the time. A template that reads every state is rendered at most once a minute; the editor says so, and naming
  the entities or a domain (`states.light`) makes it follow at once.

Under the field, **On the screen** shows the result as the screen gets it, a moment after you stop typing, with the
bytes it takes of what the screen keeps. An error is Home Assistant's own message, and the screen shows that message
too until the template works.

### How it looks: the tile's markup

Outside the braces, one line is one row on the screen.

| You write | The screen shows |
|---|---|
| `# Kitchen` (or `##`, `###`) | a heading, in the bold face |
| `Plain words` | a line in the quiet grey of a second line; long lines wrap |
| `- Empty the dishwasher` (or `*`) | a bullet, its words as quiet as a line's |
| `**75 %**` | that part bright, as the names on tiles are |
| `:good[Charged]` | that part green |
| `:alert[Rinse aid low]` | that part red |
| `:accent[Tonight]` | that part in the screen's blue |
| `\| Target \| 80 % \| 75 % \|` | a table row: up to four cells, the first names the row, the others stand right-aligned as numbers do |
| `\|---\|---\|---\|` under a row | that row is the table's head, in grey |
| an empty line | nothing: rows follow each other with the screen's own spacing |

The keys under the field put each of these in at the cursor. A line holds four parts in different colours at most;
what follows the fourth keeps the plain colour. There are no pictures, links, emoji or HTML: the screen has a fixed set
of fonts. The minus sign, dashes, curly quotes and narrow spaces a sensor may write become their plain forms (`-`,
`'`, `"`, a space); another character the fonts lack shows as an empty box.

### Examples

A list that is empty most of the day, and makes the tile disappear then:

```jinja
{% if is_state('sensor.dishwasher', 'done') %}
- Empty the **dishwasher**
{% endif %}
{% if is_state('binary_sensor.rinse_aid_low', 'on') %}
- :alert[Rinse aid] is low
{% endif %}
{% if states('sensor.waste_tomorrow') not in ['none', 'unknown'] %}
- **{{ states('sensor.waste_tomorrow') }}** goes out tonight
{% endif %}
```

A small briefing with a table:

```jinja
## Battery tonight
| | Planned | Applied |
|---|---|---|
| Target | {{ states('sensor.charge_target') }} % | {{ states('sensor.charge_target_applied') }} % |
Night power costs **€ {{ states('sensor.night_price') | float(0) | round(2) }}** per kWh.
{% if states('sensor.charge_target') == states('sensor.charge_target_applied') %}:good[On target]{% endif %}
```

The editor offers three that work in every home: the lights that are on, the doors and windows that are open, and the
weather.

## Limits

Hard numbers, so you know beforehand what works. The screen says its own in its hello (`caps`), and the app keeps to
them.

| What | Limit | Why |
|---|---|---|
| Template tiles per screen | 8 | each is a subscription in Home Assistant |
| The template | 4000 characters | far more than 24 rows need |
| Rows | 24, and what fits the tile's height | the last row that fits ends in "…" |
| Bytes of rows (after rendering) | 2048 on an ESP32-S3, 3584 on an ESP32-P4 | a state message is 4096 bytes at most |
| Table cells | 4 per row | |
| Coloured parts | 4 per row | |

Text that is longer than the tile is cut on its last line with "…". A tap on the tile does nothing.

## How it works

```text
Editor ── template ──> add-on ── render_template (one per template) ──> Home Assistant
                          <── result, again whenever an entity it reads changes ──
                       add-on: markdown -> rows (text_tile.py) ── x.md of the tile's state message ──> screen
                                                                     screen: rows -> one canvas (module_text_card)
```

- **Home Assistant renders.** The add-on subscribes to `render_template` once per template on a screen
  (`screen_manager/app/template_service.py`). Home Assistant knows which entities a template reads and sends a new
  result when one changes; it paces a template that reads the time (once a minute) or every state itself. So the add-on
  never polls, and a template is never rendered twice for two screens that show it. The template runs with the
  add-on's token: it reads what the add-on reads, which is every entity.
- **The add-on makes rows.** `text_tile.py` turns the result into rows (`{"v": 1, "r": [...]}`, or `{"v": 1, "e": why}`),
  cut to the screen's budget. `v` is the version of this form: a later syntax that a screen must read gets a new one.
  The screen gets no markdown and no Jinja, so no screen parses anything, a 4 MB board has nothing to carry, and the
  editor's preview runs the same firmware as the screen.
- **A burst is paced.** A template over many sensors renders in bursts. The add-on marks the tiles at most every half
  second, and sends only a tile whose message changed (the sync loop compares them).
- **Home Assistant away is not an error.** While the connection is down the screens keep the rows they have, and after
  it the add-on subscribes again. The error row is for a template Home Assistant refuses, in Home Assistant's words.
- **One object per card.** `module_text_card.h` plans the rows into pieces of text (which words on which line, in
  which face and colour, where the room ends) and `module_text_card.cpp` paints the plan in one LVGL object, as the
  calendar and energy cards do: a tile full of text costs one object, not a label per row. The rows and the plan are
  kept in PSRAM (`roomy.h`): on a P4 every plain allocation is internal RAM, which the network and the glass need.
  Headings take the bold label face and the rest the face a calendar's lines take, so the module brings no font: the
  4 MB boards are at their flash budget, and every board has the same fixed fonts (AGENTS.md).
- **Empty is gone.** A result without rows hides the card's ground and border, as "Background: none" does; the cells
  stay empty and nothing moves up. Tiles that move up into the room of a hidden one are a separate decision about the
  grid.

## Open points

- The add-on renders the templates of pages that are not on the glass too. That costs the add-on and Home Assistant a
  little, not the screen: a screen draws no page it does not show, and a kept page takes its card set whole. Pausing
  them needs the screen to say which page it shows, which the protocol does not do today (only the hello's `page`).
- A tap on the tile does nothing: an action aims at the tile's entity, and this tile has none. An action of its own
  (a script, a page) is a step of its own.

## The places a change touches

| Part | Files |
|---|---|
| Add-on | `text_tile.py` (rows, limits, entity facts), `template_service.py` (subscriptions), `server.py` (`subscribe_template`, `text_message`, `/api/text/preview`, `/api/text/entity`, the `text_tiles` flag), `core.py` (`screen.text`, its option), `page_layout.py` (`textTemplate`), `page_delivery.py` (`text_tiles`, `text_bytes` in caps) |
| Firmware | `modules.py`, `module_text_card.h` (data and plan), `module_text_card.cpp` and `_view.h` (paint), `runtime_model.h`, `page_receiver.cpp` (`x.md`), `runtime_tiles.h` (render, release, empty card), `hw.cpp` (caps), `packages/core.yaml` (hello `text_card`) |
| Catalogue | `catalogue/screen.yaml` `cards.text` (its price, docs/TILE_MEMORY.md) |
| Editor | `TextSection.vue`, `TemplateEditor.vue` (CodeMirror), `model/template-complete.ts`, `model/library.ts`, `tile-options.ts`, `page-validation.ts`, `pages.ts`, `types.ts` |
| Tests | `tests/test_text_tile.py`, `tests/test_text_card.cpp`, `web/tests/template-complete.spec.ts` |
