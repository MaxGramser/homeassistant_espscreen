# Layoutbot

Layoutbot is a chat in the editor that arranges a screen's pages from a sentence, such as "make a new page with two
sections where I can control all the blinds and all the curtains". It uses the AI that the person already connected to
Home Assistant, and it only ever changes the draft in the editor: it never controls a device and never saves.

| Part | Source | Test |
| --- | --- | --- |
| The question, the checked plan and the split by screen | `screen_manager/app/layoutbot.py` | `tests/test_layoutbot.py` |
| The route | `layoutbot_ask` in `screen_manager/app/server.py` (`POST api/screens/<id>/layoutbot`) | |
| The plan placed in a draft | `web/src/model/layoutbot.ts` (applyPlan) over `web/src/model/placement.ts` (placeUnits) | `web/tests/layoutbot-plan.spec.ts` |
| Restructuring a page or the screen | `layoutbot.restructured`, `web/src/model/layoutbot.ts` (applyRestructure) | `tests/test_layoutbot.py`, `web/tests/layoutbot-restructure.spec.ts` |
| What a screen takes, for the open one and the others | `web/src/editor/layoutbot.ts` | |
| The chat, the bot, the shine, sending | `web/src/components/LayoutBot.vue` (the shine, and where the chat stands), `LayoutBotChat.vue`, `LayoutBotKey.vue`, `web/src/stores/layoutbot.ts` | `web/tests/layoutbot.spec.ts` |
| On a phone: the key in the dock, the chat in a sheet | `web/src/components/ui/UiSheet.vue`, `ScreenView.vue` (`.phone-dock`) | `web/tests/layoutbot-phone.spec.ts` |
| A trial against a real Home Assistant | `diagnostics/layoutbot_trial.py` | |

## When it shows

The bot floats in the lower right corner of the editor wherever a screen is open, and on a phone it stands in the dock
at the bottom, before Add tile (see "On a phone" below). It works when Home Assistant has an
AI Task entity that can generate data (`ai_task.*` with `AITaskEntityFeature.GENERATE_DATA`, and not unavailable); the
inventory lists them under `layoutbot`. Every AI integration of Home Assistant that has AI Tasks gives one: OpenAI,
Anthropic, Google Gemini, Ollama and others. When there are several, the chat header picks one; it starts with the one
chosen in Home Assistant for "generate data" (`ai_task/preferences/get`), else the first.

Without one the bot sleeps (its eyes closed, a small "z"), and its chat says how to connect an AI instead of taking
questions: a button per integration starts that integration's setup in Home Assistant (a my link,
`/_my_redirect/config_flow_start?domain=...`), and Look again reads the inventory again once one is added.

## Where the chat stands

Whether the chat is open is in the editor's address, as everything that is open is (docs/PAGES.md, "The address"):
`#/screens/<id>?chat=layoutbot`. The bot's key pushes it, so the browser's Back (or a phone's back gesture) closes the
chat, and a reload or a kept link opens it again. Moving to another screen keeps the chat open (`ui.go("")` carries
the query), which is what Yes does on its way through the other screens and home again; the overview and the pages of
the app close it. Yes opens the screens it passes through in place of the browser's entry (`session.select(id, { replace:
true })`), so after it Back goes where the person was before, and never to a screen Yes only passed through.

### On a phone

On a phone (the editor of everyday changes, `ui.phone`) nothing floats over the page. The bot's key stands in the dock
at the bottom, before Add tile and Save & send, as tall as they are and within reach of a thumb. The chat is a sheet
from the bottom (`UiSheet`, Reka UI's Dialog, not modal), in the look of the phone's other sheets, with the safe area
below it:

- It rests at a lower height (under half the window) while the bot thinks or sends, and while its question (send it
  to the screen?) waits. The page above then shows what the answer did, since the page the answer made or changed is
  the one shown, and Show, Undo, Yes and Not now are at the bottom of the window. A tap on the grab gives the sheet its
  other height.
- It stands on the on-screen keyboard: while the keyboard is up (the visual viewport is shorter than the window) the
  sheet's bottom is the keyboard's top and it takes the room above, so the field stays in sight. The field takes no
  focus by itself on a phone, so the keyboard comes only when the person taps the field, and it is 16 px, so a
  phone's browser does not zoom the page when the field takes focus.
- Inside Home Assistant's frame, and in its Companion app, the frame may never learn of the keyboard (its visual
  viewport keeps its height). The sheet does not count on it: when the field takes focus the browser is also asked to
  bring the field into view (`scrollIntoView`, which works through the frame as for any field), and the conversation
  scrolls inside the sheet whatever its height.
- Its texts and buttons are a size larger than on a wider page; the conversation, the choices and the connect hint
  are the same component (`LayoutBotChat`).

What was tested and what was not: every control at 375 px wide in a desktop browser, light and dark, with the keyboard
imitated by a shorter visual viewport (`web/tests/layoutbot-phone.spec.ts` holds the same). Not tested: a real phone,
and the editor inside Home Assistant's Companion app, where how the frame meets the keyboard is the phone's. That
check is for a phone in the Companion app: open a screen, tap the bot, tap the field, and see that the field stays
above the keyboard while typing.

`UiSheet` (`web/src/components/ui/UiSheet.vue`) is the editor's one wrapper for a sheet from the bottom of a phone, on
Reka UI. The phone's other sheets are still built by hand (a `.sheet-dim` and a panel of their own) and are its next
users: the pages of a screen (`PhonePages.vue`), Add tile (`Library.vue` on a phone), a tile's settings (`Drawer.vue`
on a phone) and the sidebar from the left (`App.vue`, `Sidebar` with `.sheet`).

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
   loose tile named again stays where it stands. A section on a screen without sections is loose tiles. A page of the
   person's is renamed only by an item that does nothing else, here as in the add-on's check.
6. The editor takes the result as one step of undo (`applyDocument`, labelled "Layoutbot's change"), checked as any edit,
   selects the first page it made or changed, and the chat offers Show and Undo. Notes say what was left out and why.

An editor from before plans (one that sends no `version: 2`) is told to refresh the page; an add-on from before plans
(an answer without `version: 2`) is told to the person as "Update the Tessera app" and changes nothing.

After every answer that changed something the chat asks, by itself and never through the model, whether to send it:
"Shall I send it to Guition 10.1?" Yes saves the draft and sends it, as Save & send does; Not now leaves it a draft
and says so. An answer that was undone first is not sent. When the draft held changes of the person's own before the
answer, the question says that they go along.

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

## Restructuring

Two keys above the chat's field ask Layoutbot to tidy up what the person put on the screen themselves: **Restructure
this page** (the page shown) and **Restructure the whole screen**. Words in the field go along and steer the grouping
("lights first"); the key alone asks too. The editor sends `restructure: {scope: "page", page: <n>}` or
`{scope: "screen"}` beside the draft.

1. The add-on asks the AI only to group: the entities of that page (or of every page), each exactly once, by room where
   they span several, and within a room by kind, in sections with a title and an icon (`layoutbot.RESTRUCTURE_RULES`).
   It never adds or takes off a tile, and other screens are never asked about.
2. It checks the grouping (`layoutbot.restructured`): only the scope's own entities, each once; a section of one entity
   is a loose tile; an entity the model forgot goes to the page that holds most of its room, else the last, and the chat
   says how many (`kept`).
3. The editor places it (`web/src/model/layoutbot.ts applyRestructure`) through the placement Auto layout uses: it first
   counts the room the screen has without the pages it takes, then gives each tile the cards Auto layout offers the same
   entity (controls and displays from the catalogue and what Home Assistant says the entity can do) and grows them while
   the page still holds everything. A light that stays one row high with nothing else on its card gets the small
   brightness slider where it dims, so a page of many lamps is still worked from its tiles. The sections come from the
   grouping, and a page that needs more room goes on in a page right after it.
4. What the person made stays: a tile's own name, icon and colour on every card it may take, its own card where it
   stood in one cell (a meter they chose stays a meter), and tiles that are no entity of the home (a built-in, a plugin)
   as they were. A page restructured alone keeps its place, its id, its title, its icon and its top bar.
5. The last look: every tile of before must be in the result. When one would not fit (the screen's pages, its tile
   ceiling or its memory), nothing changes and the chat says why. Otherwise the result is one step of undo, with Show,
   Undo and the question whether to send it, as any answer.

Measured with gpt-4o-mini through Home Assistant 2026.11 on the Guition 10.1 (5 x 5, sections), November 2026: a page of
11 tiles in 5.1 s and one of 13 tiles in 6.4 s, both grouped into sections of lights, media and the rest. The whole
screen (46 tiles over 7 pages) in 8.7 s gave pages per room; in one run the model left out 6 tiles and in another many
more, which the check put back on their rooms' pages. A small model groups one page well and a whole screen less
reliably; nothing is ever lost.

## Which model

Home Assistant's `ai_task.generate_data` has no field for a model: the model is a setting of each AI Task in its AI
integration, and the integration's recommended settings take a small, cheap model. Layoutbot chooses which AI Task it
asks, not which model. A small model arranges a page from a sentence well enough, but groups a whole screen less
reliably (see "Restructuring"). So the chat advises, under its first message, to add an AI Task for Layoutbot to the AI
integration (OpenAI: the integration's page, Add AI Task), turn off "Recommended model settings" there and choose a
larger model, and pick that AI Task in the chat's head. The other uses of the AI integration keep the cheap one, and the
chat keeps the choice in the browser (`esp-screens.layoutbot-agent`).

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
