# The to-do card

A tile for a Home Assistant to-do list (`todo.*`): a shopping list, a list of chores, a list from Google Tasks, Todoist,
Bring, CalDAV or any other integration that gives Home Assistant a to-do list. It shows more as it gets more room, a
tap on an item ticks it off, and the screen's own keyboard adds an item. A tick made on a phone shows on every screen
a moment later.

It is part of the module `todo` (docs/MODULES.md): every board with 8 MB of flash or more has it. The CYD, the CYD
ILI9342 and the Hosyond 4-inch (4 MB) have no to-do tile: the editor does not offer to-do lists for those screens, the
app sends them no layout with one, and their firmware refuses the type.

## What it shows

The card picks its view from the room it gets, never from the board it runs on:

| Room | View | What you see |
|---|---|---|
| One cell | Count | The list's name and how many items are open. |
| A wide cell | First items | The name and the count, and beside them the first two items to tick, or their names in one line where two rows would be too low for a finger. |
| Room for the name and two rows | List | The items, each with a round box to tick, a plus key that opens the keyboard, a line that counts what does not fit, and what is done under what is open where room is left. |

A row is at least 7 mm high, so a finger hits it. A due day stands beside an item where the whole name still fits next
to it (Today, Tomorrow, the day's name in the coming week, else the date); an item that is late has a red ring and a red
day. The icon is Home Assistant's own for a to-do list, or the one chosen for the tile.

## Ticking

A tap on a row ticks the item, and a tap on a ticked item opens it again. The tick shows at once, before Home Assistant
has answered. The item keeps its place for two seconds after the last tick, so the list does not move under a finger
that ticks the next one; then it joins what is done. When Home Assistant does not confirm a tick within eight seconds,
the item goes back to what it was.

A tap anywhere else on the card opens the full screen.

## The full screen

The whole list in one column that scrolls: a field that opens the keyboard, the open items, and under **Completed**
what is done. A tap on the bin beside Completed asks once and then removes every completed item.

A swipe to the left on an item brings **Rename** and **Remove** in from the row's end, as far as the finger draws them:
past a third of the way they stay, less lets them go back. The item's name stays where it is, so it is clear whose keys
they are. A tap on one acts on the item, a tap anywhere else or a scroll puts them away. Only the row's own strip is
drawn again while the keys move, and nothing is planned again, so they follow the finger on every board.

Holding an item opens a small sheet with the same two keys, for a finger that does not swipe. Rename opens the
keyboard with the item's name in the field.

## The keyboard

The first keyboard of the firmware. It is a sheet at the bottom of the glass, never wider than 16.5 cm, with keys of at
most 9 mm; on glass too short to keep the list above it, it takes the whole glass, so its keys stay at least 6.5 mm
high.

- One layout, QWERTY, with a page of digits (`123`) and a page of signs (`#+=`).
- Holding a letter shows its accents in a strip above it (é è ê ë for e); a tap takes one.
- The first letter of an item is a capital, and holding backspace keeps erasing.
- The row of offered names keeps its room while the list has names to offer, so the keys never move while you type.
- The check key and the blue plus add what the field holds. The keyboard stays up for the next item, and the empty
  field says what was added.
- Above the keys stand the names of items that were ticked off before, the last one first, and only those that begin
  with what is typed. A tap on one puts it back on the list.
- Adding a name that is already on the list as a completed item opens that item again instead of writing it twice, and
  a name that is already open is not added a second time.

Every character a key types is one the screens' fonts have. A name with a character the fonts lack (an emoji typed on
a phone) shows an empty box in its place.

## The card's choices

Set in the editor's inspector for the tile:

- **Order**: as in Home Assistant, by name, or by due date. These are the orders of Home Assistant's own to-do list
  card; what is open and what is done are each ordered on their own.
- **Completed items**: shown under the open items, or left out.
- **Due dates**: the day beside an item, or left out.
- **Add items**: the plus key, the field and the keyboard.
- **Suggest names**: the names above the keys.
- **Remove completed**: the bin in the full screen.

What a list cannot do in Home Assistant is not offered on the screen either: a list that takes no new items has no
plus key, one that cannot change an item has no rows to tick, and one that cannot delete has no bin and no Remove.

## How the items reach the screen

A to-do list's state in Home Assistant is only the number of open items. The items come from the websocket command
`todo/item/subscribe`, which sends the whole list once and again after every change.

```text
Home Assistant ── todo/item/subscribe: the whole list after every change ──> app
app: order, cut to what the screen keeps ── x.todo of the tile's state message ──> screen
screen: a tap, the keyboard ── event esphome.screen_todo ──> app ── todo.update_item, add_item, remove_item ──> Home Assistant
```

- **One subscription per list**, shared by every screen that shows it (`todo_feed.TodoService`). After a new connection
  to Home Assistant the app subscribes again; the screens keep the items they have meanwhile.
- **The screen never sees a uid.** The app gives every item a small number that it never gives twice, and the screen
  names an item by that number. A number from an older list names the same item or none, so a list that changed under
  a finger never ticks the wrong item.
- **The items travel in the tile's state message** (`x.todo`): what the screen may do with the list, how many items are
  open and done in all, the items in the tile's order (the open ones first), and the names to offer. A screen says in
  its hello how many items it keeps (`todo_items`, 40); a longer list is cut and its rest counted, never dropped in
  silence. A name is cut to 64 bytes with an ellipsis.
- **A due day travels as days from today**, and late as a flag. The app sends a list with due dates again each minute,
  so an item turns late and tomorrow turns into today without a change in Home Assistant.
- **The screen asks, the app acts.** A tick, a new item, a new name and a removal are the event `esphome.screen_todo`
  with the tile's place, the action and the item's number or the typed text. The app checks that the tile's choices and
  the list's features allow it and calls Home Assistant's own action. The list's change comes back through the
  subscription, to every screen that shows the list.

## Where it lives

| Part | File |
|---|---|
| The views, the full screen and the keyboard, planned | `components/smart_display/module_todo.h` |
| Painting a plan, the finger, the requests | `components/smart_display/module_todo.cpp`, `module_todo_view.h` |
| Ordering, packing, the items' numbers, the subscriptions, a request's action | `screen_manager/app/todo_feed.py` |
| The type | `catalogue/todo.yaml` |
| The inspector's section | `web/src/components/inspector/TodoSection.vue` |
| Tests | `tests/test_todo.cpp`, `tests/test_todo_feed.py` |
| The real firmware drawing and tapping it on the host | `tools/render/run.py --only todo` |

## The places a change touches

| Part | Files |
|---|---|
| Add-on | `todo_feed.py`, `server.py` (`subscribe_todo`, `todo_loop`, `answer_todo`, `sync_todos`, `todo_extras`, the `todo_lists` flag), `core.py` (the options), `page_layout.py`, `page_delivery.py` (`todo_items` in caps), `page_service.py` (`todo_due`) |
| Firmware | `modules.py`, `module_todo.h`, `module_todo.cpp`, `module_todo_view.h`, `runtime_model.h`, `page_receiver.cpp` (`x.todo`), `runtime_tiles.h` (render, tap, full screen, close), `hw.cpp` (caps), `packages/core.yaml` (hello `todo_card`) |
| Catalogue | `catalogue/todo.yaml`, `catalogue/_ha.json`, `tile_icons.py` (the icon) |
| Editor | `TodoSection.vue`, `TileInspector.vue`, `model/tile-options.ts`, `pages.ts`, `page-validation.ts`, `layout.ts`, `library.ts`, `tile-text.ts`, `types.ts` |
| Texts | `screen.todo`, `editor.tile.todo`, `editor.domains.todo`, `editor.library.filters.todo`, `editor.mockup.todo_*` |
