# Layoutbot

Layoutbot is a chat in the editor that arranges a screen's pages from a sentence, such as "make a new page with two
sections where I can control all the blinds and all the curtains". It uses the AI that the person already connected to
Home Assistant, and it only ever changes the draft in the editor: it never controls a device and never saves.

| Part | Source | Test |
| --- | --- | --- |
| The question, the plan and the draft that follows | `screen_manager/app/layoutbot.py` | `tests/test_layoutbot.py` |
| The route | `layoutbot_ask` in `screen_manager/app/server.py` (`POST api/screens/<id>/layoutbot`) | |
| The chat, the bot and the shine | `web/src/components/LayoutBot.vue`, `web/src/stores/layoutbot.ts` | `web/tests/layoutbot.spec.ts` |
| A trial against a real Home Assistant | `diagnostics/layoutbot_trial.py` | |

## When it shows

The bot floats over the lower right corner of the pages only when Home Assistant has an AI Task entity that can
generate data (`ai_task.*` with `AITaskEntityFeature.GENERATE_DATA`, and not unavailable). The inventory lists them
under `layoutbot`; without one the editor shows nothing of Layoutbot. Every AI integration of Home Assistant that has
AI Tasks gives one: OpenAI, Anthropic, Google Gemini, Ollama and others. When there are several, the chat header picks
one; it starts with the one chosen in Home Assistant for "generate data" (`ai_task/preferences/get`), else the first.

## How a question becomes a draft

1. The editor sends the sentence and its draft as it is (`layout`, the page document) to the add-on.
2. The add-on asks Home Assistant's `ai_task.generate_data` with a fixed `structure` (`layoutbot.STRUCTURE`). The
   instructions hold the screen's grid and limits, whether it draws sections, the icons, the existing pages with their
   sections and entities, and one line per entity of the inventory (id, name, area). Home Assistant turns the
   structure into a JSON schema for the provider (`helpers/llm.py selector_serializer`), so every provider gets the
   same one, with structured output where the provider has it.
3. The answer is a plan, not a document: `reply` (a sentence to the person), `pages` (each a new page or the number of
   an existing one, with a title, an icon, `sections` of entity ids and loose `tiles`) and `remove` (entity ids).
4. `apply_plan` makes the draft from the plan with the same rules as the editor: new ids, the Home page's top bar on a
   new page, sections as blocks at the first free place (side by side when they are narrow), and a page that is full
   going on in a page after it. An entity id that is not in the inventory is left out with a note. An entity the plan
   puts in a section of a page it already stands on moves there; one it names again as a loose tile stays where it
   stands. A new page with nothing on it is not made.
5. A new page is dressed: every tile starts as one cell, then gets its next face while the page still holds everything,
   the types with the most to show first (players and climate, then cameras and vacuums, then lights and covers). The
   faces come from what the entity offers in Home Assistant through the catalogue (`ha.capabilities`, the same answer
   the editor's drawer uses): wide with a control of one row (a light's brightness, a cover's buttons, a player's keys),
   then 2 x 2 with a control of two rows (a light's brightness and presets, a player's volume and keys, a thermostat's
   setpoint and mode). A camera's larger face is its larger picture. A small grid keeps every tile rather than growing
   a few.
6. The result goes through `validate_document` like any save, and back to the editor with the reply and the notes in
   the editor's language. The editor takes it as one step of undo (`applyDocument`, labelled "Layoutbot's change"),
   selects the first page it made or changed, and the chat offers Show and Undo.

While the question is out the pages wait: a veil with a light sweeping over it covers them, a pill says how long it has
been, and no click or key reaches the editor except Escape, which stops waiting. An answer that comes after Stop, or
for a draft that changed meanwhile (another tab's save), is left unused and the chat says so.

## What it can never do

- **Control a device.** The plan has no field for an action; the only Home Assistant action the add-on calls is
  `ai_task.generate_data`. "Turn on the living room lights" gets a sentence back and no change.
- **Save.** The answer is a draft; the person saves it as any other edit, or undoes it.
- **Show an entity that does not exist, or a control an entity cannot draw.** Ids are checked against the inventory,
  controls against what the entity offers.

## Privacy and cost

With a cloud model, the question, the screen's pages and the id, name and area of every entity the editor lists go to
that provider, as with any AI Task of Home Assistant. The chat says so in its first message, with the model's name.
A home of about 1000 entities makes instructions of about 60 kB (about 15 000 tokens), so one question to a small cloud
model costs a fraction of a cent. A local model (Ollama) keeps everything in the house.

## Measured

On a Home Assistant 2026.11.0 with the OpenAI integration's AI Task on its recommended settings (gpt-4o-mini), a home of
997 entities, the Guition 10.1 (5 x 5, sections), November 2026:

| Question | Seconds | Result |
| --- | --- | --- |
| A new page with two sections, all the blinds and all the curtains (Dutch, and English) | 4.9 to 8.0 | valid; two sections, covers wide with their buttons; one blind sorted with the curtains in some runs |
| A music page with all the speakers | 4.6 to 8.1 | valid; players 2 x 2 with volume and keys |
| All the lights on one page, a section per room | 8.1 to 14.9 | valid; continued on a second page when a 5 x 5 page was full |
| A climate page with the air conditioning and the temperatures | 7.5 | valid; the thermostat 2 x 2 with setpoint and mode, sensors one cell |
| Rename page 2 | 3.1 | exact |
| Take one player off the living room page | 6.8 | exact |
| Put the kitchen lights on page 3 in a section | 5.6 | valid; the lights moved into the new section |
| Turn on all the lights in the living room | 1.8 to 3.1 | no change, "I can only change the layout" |

Every answer of the last rounds gave a valid draft. What a small model gets wrong is which entity is what: a sensor of
the same room among its lights, a blind among the curtains. Device classes in the entity lines would help it (see
below). A flat list of operations made gpt-4o-mini stop after the first one and write `},{` into a text field; the
nested, declarative plan of pages and sections does not.

## How it was chosen

Home Assistant offers four ways to an LLM; the source of `home-assistant/core` (2026.12 dev) settles which fits:

- **The conversation API** (`conversation/process`, agents from `conversation/agent/list`) returns speech text only,
  and the agent runs with the person's chosen LLM API, which may control devices. No structure, and the wrong rights.
- **AI Task** (`ai_task.generate_data`, 2025.8+) takes instructions and a `structure` of selectors and returns `data`,
  as JSON where a structure is given. OpenAI, Anthropic, Google and Ollama implement it with their structured output.
  It runs without the Assist API unless code inside Home Assistant passes one, so the model has no tools at all. The
  add-on reaches it with its Supervisor token like any action. **This is the route.**
- **A custom LLM API** (`homeassistant.helpers.llm.async_register_api`) would need code inside Home Assistant, a custom
  integration of our own.
- **MCP**: Home Assistant's `mcp` client integration registers the tools of an MCP server as an LLM API, and since
  2026.9 an app can announce its MCP server through Supervisor discovery (`async_step_hassio`). The add-on could serve
  layout tools that way, so the person's own voice assistant could arrange a screen. That is a later step: the agent
  would then also hold the Assist API, and the editor would not see the change before it is made.

## Later

- An API key of its own (an OpenAI or Anthropic key in the app) for a Home Assistant without an AI Task.
- Device classes and Home Assistant's floors in the entity lines (the auto-layout maker reads them already), so "all
  blinds" and "per floor" are sure.
- Only the entities exposed to Assist, as a choice, for people who want less to leave the house.
- The layout tools as an MCP server announced to Home Assistant (above).
