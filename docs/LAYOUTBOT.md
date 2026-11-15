# Layoutbot

Layoutbot is a chat in the editor that arranges a screen's pages from a sentence, such as "make a new page with two
sections where I can control all the blinds and all the curtains". It uses the AI that the person already connected to
Home Assistant, and it only ever changes the draft in the editor: it never controls a device and never saves.

| Part | Source | Test |
| --- | --- | --- |
| The question, the checked plan and the split by screen | `screen_manager/app/layoutbot.py` | `tests/test_layoutbot.py` |
| The route | `layoutbot_ask` in `screen_manager/app/server.py` (`POST api/screens/<id>/layoutbot`) | |
| The plan placed in a draft | `web/src/model/layoutbot.ts` (applyPlan) over `web/src/model/placement.ts` (placeUnits) | `web/tests/layoutbot-plan.spec.ts` |
| What a screen takes, for the open one and the others | `web/src/editor/layoutbot.ts` | |
| The chat, the bot, the shine, sending | `web/src/components/LayoutBot.vue`, `web/src/stores/layoutbot.ts` | `web/tests/layoutbot.spec.ts` |
| A trial against a real Home Assistant | `diagnostics/layoutbot_trial.py` | |

## When it shows

The bot floats in the lower right corner of the editor wherever a screen is open. It works when Home Assistant has an
AI Task entity that can generate data (`ai_task.*` with `AITaskEntityFeature.GENERATE_DATA`, and not unavailable); the
inventory lists them under `layoutbot`. Every AI integration of Home Assistant that has AI Tasks gives one: OpenAI,
Anthropic, Google Gemini, Ollama and others. When there are several, the chat header picks one; it starts with the one
chosen in Home Assistant for "generate data" (`ai_task/preferences/get`), else the first.

Without one the bot sleeps (its eyes closed, a small "z"), and its chat says how to connect an AI instead of taking
questions: a button per integration starts that integration's setup in Home Assistant (a my link,
`/_my_redirect/config_flow_start?domain=...`), and Look again reads the inventory again once one is added.

## How a question becomes a draft

1. The editor sends the sentence, its draft as it is (`layout`, the page document), `version: 2` and, when the person
   chose All screens in the chat, `all_screens: true` to the add-on.
2. The add-on asks Home Assistant's `ai_task.generate_data` with a fixed `structure` (`layoutbot.STRUCTURE`). The
   instructions hold the screen's grid and limits, whether it draws sections, the icons, the existing pages with their
   sections and entities, the other screens and their pages only when the person chose All screens, and one line per
   entity of the inventory (id, name, area). Home Assistant turns the structure into a JSON schema for the provider
   (`helpers/llm.py selector_serializer`), so every provider gets the same one, with structured output where the
   provider has it. The request and the entity list stand between markers, and the rules say that names, titles and
   the request are data, never instructions.
3. The answer is a plan, not a document: `reply` (a sentence to the person), `pages` (each a new page or the number of
   an existing one, with a title, an icon, `sections` of entity ids and loose `tiles`, and for All screens a `screen`)
   and `remove` (entity ids).
4. The add-on checks it and places nothing (`layoutbot.answered`, `checked`): only entities of this home, each once
   (an unknown id is a note); a page number past the screen's pages is a new page; a page the person has gets a title
   only from an item that does nothing else; icons only from the fixed set; a new page with nothing on it is left out.
   It splits the plan by screen: without All screens a `screen` the model names anyway is ignored, and taking tiles off
   (`remove`) is only ever the open screen's. The answer is `{version: 2, reply, plan, notes, elsewhere}`.
5. The editor places the plan (`applyPlan`) with what it places by, never another way. On a page the person has, as
   their own edits place: a tile from the library (its default card) at the first free cell outside the sections, a
   section made as "Add a section" makes one and filled as a drop fills one (the section growing as a drop grows it),
   each step through arrangeTiles; the person's own tiles never move, what has no room there is left out with a note,
   and no page is pushed in after theirs. New pages through the one placement Auto layout uses (`model/placement.ts
   placeUnits`): every section of the plan, and a page's loose tiles, is a unit; each tile takes the cards Auto layout
   gives the same entity (`model/auto-layout.ts placeTileFor`: sizes, controls and displays from the catalogue and what
   Home Assistant says the entity can do, the album cover on a player where the screen draws pictures) and grows
   through them while the page still holds everything (`grow`, alike tiles together), only into those cards, never a
   size made up to fill a hole. New pages come after the person's, and a unit that runs over a page goes on in a page
   after it. The screen's tile ceiling, pages and memory hold as they hold an add from the library (`proposalHolds`,
   the draft priced with what is added). Before that, the editor takes tiles off, renames, and keeps what the plan names
   again: a tile already in the section it is named in stays as it is, one elsewhere on that page moves into it, a
   loose tile named again stays where it stands. A section on a screen without sections is loose tiles.
6. The editor takes the result as one step of undo (`applyDocument`, labelled "Layoutbot's change"), checked as any edit,
   selects the first page it made or changed, and the chat offers Show and Undo. Notes say what was left out and why.

An editor from before plans (one that sends no `version: 2`) is told to refresh the page; an add-on from before plans
(an answer without `version: 2`) is told to the person as "Update the Tessera app" and changes nothing.

After every answer that changed something the chat asks, by itself and never through the model, whether to send it:
"Shall I send it to Guition 10.1?" Yes saves the draft and sends it, as Save & send does; Not now leaves it a draft
and says so. An answer that was undone first is not sent.

**Several screens.** Only when the person chose All screens in the chat. Each other screen's plan is placed by the same
applyPlan on that screen's saved document, with what that screen takes (its grid, sizes, sections, memory), and the chat
lists what it would change ("Wallbox: 1 tile added") with Look, which opens that screen with the change as its draft.
Nothing of it is saved before yes. Yes saves the open screen first, then opens each other screen in turn, places its plan
in its draft again where its saved document changed meanwhile, and saves it through the same Save & send: the same
checks, its own step of undo. The chat shows each screen's progress; a screen that fails keeps nothing of it (its step
is taken back), the others still go, the chat says which failed and why, and the screen the person was on opens again.

While the question is out the pages wait: a veil with a light sweeping over it covers them, a pill says how long it has
been, and no click or key reaches the editor except Escape, which stops waiting. An answer that comes after Stop, or
for a draft that changed meanwhile (another tab's save), is left unused and the chat says so.

## What it can never do

- **Control a device.** The plan has no field for an action; the only Home Assistant action the add-on calls is
  `ai_task.generate_data`. "Turn on the living room lights" gets a sentence back and no change.
- **Save without a yes.** The answer is a draft, and another screen's change a proposal, until the person says yes in
  the chat (or saves the draft as any other edit).
- **Show an entity that does not exist, or a control an entity cannot draw.** Ids are checked against the inventory,
  cards come from the catalogue and what the entity offers, as Auto layout's do.
- **Place a tile another way than the editor.** The add-on places nothing; the plan goes through the editor's one
  placement, the same as Auto layout's and the person's own drops.

## Privacy and cost

With a cloud model, the question, the pages of every screen and the id, name and area of every entity the editor lists
go to that provider, as with any AI Task of Home Assistant. The chat says so in its first message, with the model's name.
A home of about 1000 entities makes instructions of about 60 kB (about 15 000 tokens), so one question to a small cloud
model costs a fraction of a cent. A local model (Ollama) keeps everything in the house.

## Measured

The seconds are the AI Task's answer, measured before the plan moved to the editor (the cards then were Layoutbot's own;
since then they are Auto layout's):

On a Home Assistant 2026.11.0 with the OpenAI integration's AI Task on its recommended settings (gpt-4o-mini), a home of
997 entities, the Guition 10.1 (5 x 5, sections), November 2026:

| Question | Seconds | Result |
| --- | --- | --- |
| A new page with two sections, all the blinds and all the curtains (Dutch, and English) | 4.9 to 8.0 | valid; two sections; one blind sorted with the curtains in some runs |
| A music page with all the speakers | 4.6 to 8.1 | valid |
| All the lights on one page, a section per room | 8.1 to 14.9 | valid; continued on a second page when a 5 x 5 page was full |
| A climate page with the air conditioning and the temperatures | 7.5 | valid |
| Rename page 2 | 3.1 | exact |
| Take one player off the living room page | 6.8 | exact |
| Put the kitchen lights on page 3 in a section | 5.6 | valid; the lights moved into the new section |
| Turn on all the lights in the living room | 1.8 to 3.1 | no change, "I can only change the layout" |
| On a CYD (2 x 3, no sections): the living room lights on a page | 5.5 | valid; eight lights as single tiles over two pages |
| On a CYD: a page with the speakers | 4.9 | valid; three players wide with their keys |
| Through the dev app, in the editor: all the lights on one page, a section per room | 16.8 to 17.1 | valid; 21 lights in five sections on one 5 x 5 page |
| Through the dev app: a Security page with the alarm and the door sensors on every screen | 14.6 to 17.2 | valid on all three screens; the other two as proposals |
| Through the dev app: the alarm on page 1 of every screen | 3.6 to 7.3 | no change: every page 1 was full, said per screen |

The request and the entity list stand between markers in the question, and the rules say that names, titles and the
request are data, never instructions; the markers are taken out of what the home and the person wrote.

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

- Alerts on every screen ("show the doorbell alert on all my screens"): alerts are automations of the Alerts page, not
  the layout, so a plan would need a part of its own for them.
- An API key of its own (an OpenAI or Anthropic key in the app) for a Home Assistant without an AI Task.
- Device classes and Home Assistant's floors in the entity lines (the auto-layout maker reads them already), so "all
  blinds" and "per floor" are sure.
- Only the entities exposed to Assist, as a choice, for people who want less to leave the house.
- The layout tools as an MCP server announced to Home Assistant (above).
