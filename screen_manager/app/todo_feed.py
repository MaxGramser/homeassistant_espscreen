"""The to-do card's items: what a to-do tile shows, as Home Assistant has them, ordered by the tile's own choices and
packed for the screen (components/smart_display/module_todo.h reads it as `x.todo`).

Home Assistant is the source. A list's state is only the number of open items; the items come from the websocket
command `todo/item/subscribe`, which sends the whole list again whenever it changes (homeassistant/components/todo).
The app keeps one subscription per list (TodoService) and marks the list's tiles when a new one arrives, so a tick on a
phone shows on every screen without polling. docs/TODO.md says more.

The screen never sees a uid: every item travels with a small number the app keeps for it, and a tick, a new item, a
new name or a removal comes back as the event `esphome.screen_todo` with that number, which the app turns into Home
Assistant's own action (`request`). A number that no longer names an item does nothing, so a list that changed under a
finger never ticks the wrong item.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta

# ---- The tile's own choices (validated in core.validate_layout; the inspector writes them). The orders are Home
# Assistant's own (the to-do list card's display_order).
ORDERS = ('none', 'alpha_asc', 'alpha_desc', 'duedate_asc', 'duedate_desc')
# option: its default. The app keeps them all: the screen gets the items already ordered and what it may do as flags.
DEFAULTS = {'todo_order': ORDERS[0], 'todo_completed': True, 'todo_due': True, 'todo_add': True, 'todo_suggest': True,
            'todo_clear': True}
KEYS = tuple(DEFAULTS)
OWN = KEYS

# TodoListEntityFeature (homeassistant/components/todo/const.py).
CREATE, DELETE, UPDATE = 1, 2, 4
# What the screen may do with the list (`f` of the card): add an item, tick one, remove one, remove what is done,
# rename one.
MAY_ADD, MAY_TICK, MAY_REMOVE, MAY_CLEAR, MAY_RENAME = 1, 2, 4, 8, 16
# An item's flags (`[number, flags, summary, days?]`).
DONE, LATE = 1, 2

# Room for the card's part of the state message: the whole message stays under 4096 bytes (page_delivery.MAX_MESSAGE).
BUDGET = 2600
SUMMARY_BYTES = 64
# What a new item or a new name may hold (the screen's field holds as much).
TEXT_BYTES = 120
# The items a screen keeps (module_todo.h), unless its hello states its own (`todo_items`); suggestions beside them.
KEEPS, KEEPS_MAX = 40, 120
SUGGESTIONS, SUGGESTION_BYTES = 12, 32
# The screen's feature, the event it asks with, and the actions that event names.
FEATURE = 'todo_card'
MODULE = 'todo'
EVENT = 'esphome.screen_todo'
ACTIONS = ('tick', 'untick', 'add', 'rename', 'remove', 'clear')
ELLIPSIS = '…'


def validate(options):
    """The to-do choices of a tile's options, checked and without defaults; ValueError(key) on a wrong one."""
    out = dict(options)
    for key, default in DEFAULTS.items():
        if key not in out:
            continue
        if key == 'todo_order':
            if out[key] not in ORDERS:
                raise ValueError(key)
        elif not isinstance(out[key], bool):
            raise ValueError(key)
        if out[key] == default:
            del out[key]
    return out


def choice(tile, key):
    value = (tile.get('options') or {}).get(key)
    return DEFAULTS[key] if value is None else value


def cut(text, limit):
    """`text` in at most `limit` bytes of UTF-8, ending in an ellipsis when it was longer."""
    text = ' '.join(str(text or '').split())
    if len(text.encode()) <= limit:
        return text
    room = limit - len(ELLIPSIS.encode())
    while len(text.encode()) > room:
        text = text[:-1]
    return text.rstrip() + ELLIPSIS


def keeps(caps=None):
    """How many items a screen keeps: what its hello states (`todo_items`), else KEEPS."""
    value = (caps or {}).get('todo_items') if isinstance(caps, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 < value <= KEEPS_MAX else KEEPS


def due_of(item, tz, now):
    """(days from today, late) of an item's due date, or None. A date without a time is due until that day ends
    (the frontend's rule, hui-todo-list-card.ts)."""
    raw = item.get('due')
    if isinstance(raw, datetime):
        moment = raw
    elif isinstance(raw, date):
        return (raw - now.astimezone(tz).date()).days, raw < now.astimezone(tz).date()
    elif isinstance(raw, str) and raw:
        try:
            if 'T' not in raw:
                day = date.fromisoformat(raw)
                return (day - now.astimezone(tz).date()).days, day < now.astimezone(tz).date()
            moment = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=tz)
    return (moment.astimezone(tz).date() - now.astimezone(tz).date()).days, moment < now


def ordered(items, order, tz, now):
    """The items of one section in the tile's order; `none` keeps Home Assistant's own."""
    if order in ('alpha_asc', 'alpha_desc'):
        return sorted(items, key=lambda i: str(i.get('summary') or '').casefold(), reverse=order == 'alpha_desc')
    if order in ('duedate_asc', 'duedate_desc'):
        far = timedelta(days=10 ** 6).days
        def key(item):
            due = due_of(item, tz, now)
            # Without a date: last going up, first going down.
            return due[0] if due else far
        return sorted(items, key=key, reverse=order == 'duedate_desc')
    return list(items)


def done(item):
    return item.get('status') == 'completed'


def flags(tile, features):
    """What the screen may do with this list: Home Assistant's features of the list and the tile's choices."""
    features = features if isinstance(features, int) and not isinstance(features, bool) else 0
    out = 0
    if features & CREATE and choice(tile, 'todo_add'):
        out |= MAY_ADD
    if features & UPDATE:
        out |= MAY_TICK | MAY_RENAME
    if features & DELETE:
        out |= MAY_REMOVE
        if choice(tile, 'todo_clear'):
            out |= MAY_CLEAR
    return out


def suggestions(items):
    """What typing may offer: the names of what is done, the last one first, each once and none that is open again."""
    open_names = {str(i.get('summary') or '').casefold() for i in items if not done(i)}
    def when(pair):
        index, item = pair
        return (str(item.get('completed') or ''), index)
    out, seen = [], set(open_names)
    for _, item in sorted(((n, i) for n, i in enumerate(items) if done(i)), key=when, reverse=True):
        name = ' '.join(str(item.get('summary') or '').split())
        if not name or name.casefold() in seen or len(name.encode()) > SUGGESTION_BYTES:
            continue
        seen.add(name.casefold())
        out.append(name)
        if len(out) == SUGGESTIONS:
            break
    return out


def card(tile, items, numbers, features, tz, now, most=KEEPS):
    """The `x.todo` of a to-do tile: what the screen may do, how many items are open and done in all, and the items
    it shows: the open ones in the tile's order, then the done ones, as many as the screen keeps and the message holds.
    `items` is Home Assistant's list (None: not known yet), `numbers` gives an item's number by its uid."""
    if items is None:
        return {'v': 1, 'w': 1}
    order = choice(tile, 'todo_order')
    open_items = ordered([i for i in items if not done(i)], order, tz, now)
    done_items = ordered([i for i in items if done(i)], order, tz, now)
    may = flags(tile, features)
    out = {'v': 1, 'f': may, 'n': len(open_items), 'd': len(done_items), 'i': []}
    show_due = choice(tile, 'todo_due')
    used = 96
    rows = open_items + (done_items if choice(tile, 'todo_completed') else [])
    for item in rows[:most]:
        number = numbers.get(item.get('uid'))
        if number is None:
            continue
        row = [number, DONE if done(item) else 0, cut(item.get('summary'), SUMMARY_BYTES)]
        due = due_of(item, tz, now) if show_due and not done(item) else None
        if due:
            row[1] |= LATE if due[1] else 0
            row.append(max(-9999, min(9999, due[0])))
        size = len(row[2].encode()) + 24
        if used + size > BUDGET:
            break
        used += size
        out['i'].append(row)
    if may & MAY_ADD and choice(tile, 'todo_suggest'):
        offered = []
        for name in suggestions(items):
            size = len(name.encode()) + 4
            if used + size > BUDGET:
                break
            used += size
            offered.append(name)
        if offered:
            out['s'] = offered
    return out


def unsupported(tiles, features):
    """Whether a layout has a to-do tile a screen with these hello `features` (None: not known yet) cannot draw: the
    card is the module todo's, on boards with 8 MB of flash or more."""
    return any(str(tile.get('entity') or '').startswith('todo.') for tile in tiles) and FEATURE not in (features or ())


# The firmware that draws the card, named to a screen that cannot take a layout with one.
FIRMWARE = '0.61.0'


class Numbers:
    """A small number for every item of every list, kept while the app runs: the screen names an item by it. A number
    is never given twice, so one that came from an older list names the same item or none."""

    def __init__(self):
        self.by_uid = {}   # entity -> {uid: number}
        self.next = 1

    def update(self, entity, items):
        known = self.by_uid.get(entity) or {}
        fresh = {}
        for item in items or []:
            uid = item.get('uid')
            if not isinstance(uid, str) or not uid or uid in fresh:
                continue
            number = known.get(uid)
            if number is None:
                number, self.next = self.next, self.next + 1
                if self.next > 2_000_000_000:
                    self.next = 1
            fresh[uid] = number
        self.by_uid[entity] = fresh
        return fresh

    def of(self, entity):
        return self.by_uid.get(entity) or {}

    def uid(self, entity, number):
        for uid, known in self.of(entity).items():
            if known == number:
                return uid
        return None

    def forget(self, entity):
        self.by_uid.pop(entity, None)


def request(action, items, uid, text, features):
    """Home Assistant's action for what a screen asks of a list: (service, data) for the `todo` domain, or None when
    there is nothing to do. `uid` is the item the screen named (None for add and clear), `text` what it typed.
    Adding a name that is already on the list brings that item back instead of writing it twice."""
    features = features if isinstance(features, int) and not isinstance(features, bool) else 0
    text = cut(text, TEXT_BYTES).rstrip(ELLIPSIS).strip() if isinstance(text, str) else ''
    items = items or []
    if action in ('tick', 'untick'):
        if not uid or not features & UPDATE:
            return None
        return 'update_item', {'item': uid, 'status': 'completed' if action == 'tick' else 'needs_action'}
    if action == 'add':
        if not text:
            return None
        same = [i for i in items if ' '.join(str(i.get('summary') or '').split()).casefold() == text.casefold()]
        if any(not done(i) for i in same):
            return None
        if same and features & UPDATE and same[0].get('uid'):
            return 'update_item', {'item': same[0]['uid'], 'status': 'needs_action'}
        if not features & CREATE:
            return None
        return 'add_item', {'item': text}
    if action == 'rename':
        if not uid or not text or not features & UPDATE:
            return None
        return 'update_item', {'item': uid, 'rename': text}
    if action == 'remove':
        if not uid or not features & DELETE:
            return None
        return 'remove_item', {'item': uid}
    if action == 'clear':
        if not features & DELETE or not any(done(i) for i in items):
            return None
        return 'remove_completed_items', {}
    return None


class TodoService:
    """One subscription per to-do list that a screen shows. `ha` subscribes (`subscribe_todo(entity, callback)`,
    `unsubscribe_todo(id)`), says whether it is `online` and which `connection` it is on, and takes the lists that
    changed (`dirty`, `changed`) so the sync loop sends their tiles again."""

    def __init__(self, ha, clock=time.monotonic):
        self.ha = ha
        self.clock = clock
        self.items = {}    # entity -> the list as Home Assistant sent it last
        self.subs = {}     # entity -> (subscription id, connection)
        self.numbers = Numbers()

    async def sync(self, wanted):
        """Subscribe the lists in `wanted` that are not yet, and end the ones no screen shows any more. After a new
        connection to Home Assistant every list is subscribed again; the screens keep what they have meanwhile."""
        wanted = set(wanted)
        connection = getattr(self.ha, 'connection', 0)
        online = getattr(self.ha, 'online', True)
        for entity, (key, on) in list(self.subs.items()):
            if entity in wanted and on == connection:
                continue
            if key is not None and on == connection and online:
                try:
                    await self.ha.unsubscribe_todo(key)
                except (ConnectionError, TimeoutError):
                    pass
            del self.subs[entity]
        for entity in list(self.items):
            if entity not in wanted:
                del self.items[entity]
                self.numbers.forget(entity)
        if not online:
            return
        for entity in sorted(wanted - set(self.subs)):
            try:
                key = await self.ha.subscribe_todo(entity, lambda event, entity=entity: self.received(entity, event))
            except TimeoutError:
                return
            except ConnectionError as error:
                # Home Assistant refuses a list it does not have; without a connection the next pass tries again.
                if getattr(error, 'detail', None) is None:
                    return
                key = None
            self.subs[entity] = (key, connection)

    def received(self, entity, event):
        items = (event or {}).get('items') if isinstance(event, dict) else None
        if not isinstance(items, list):
            return
        items = [i for i in items if isinstance(i, dict)]
        if self.items.get(entity) == items:
            return
        self.items[entity] = items
        self.numbers.update(entity, items)
        self.ha.dirty.add(entity)
        self.ha.changed.set()
        events = getattr(self.ha, 'state_events', None)
        if events is not None:
            events.notify(entity)

    def of(self, entity):
        """The list's items, or None while Home Assistant has not sent them."""
        return self.items.get(entity)


def wanted_lists(tile_lists):
    """The to-do lists of every screen's tiles."""
    return {tile['entity'] for tiles in tile_lists for tile in tiles or []
            if isinstance(tile, dict) and str(tile.get('entity') or '').startswith('todo.')}
