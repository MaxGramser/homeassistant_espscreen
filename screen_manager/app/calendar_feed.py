"""The calendar card's events (firmware 0.56.0): what a calendar tile shows, fetched from Home Assistant, filtered by the
tile's own choices and packed for the screen (components/smart_display/calendar_card.h reads it as `x.cal`).

Home Assistant is the source: `calendar.get_events` for every calendar of a card in one call (Home Assistant expands
repeating events itself), the colour Home Assistant gives a calendar (its registry's `options.calendar.color`, else the
frontend's palette by the calendar's place among all calendars, as its calendar panel colours them), and its own names.
A date without a time is an all-day event whose end does not count (Home Assistant's rule). docs/CALENDAR.md says more.

A screen whose hello says `calendar_detail` gets each event short (`compact`): what its views draw, a title and a place
cut with an ellipsis, so a busy week fits the message; a tap on an event asks for the rest (`detail`, the screen's
`esphome.screen_calendar`, answered with op `calendar_event`). Every screen gets at most the events it keeps (`most`),
the nearest first, and the count of the rest.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time as day_time, timedelta

# ---- The tile's own choices (validated in core.validate_layout; the inspector writes them).
STYLES = ('events', 'busy_free', 'room')
WEEK_STARTS = ('today', 'monday')
BOOK_TEXT = 48
CREATE_EVENT = 1  # CalendarEntityFeature.CREATE_EVENT: the calendar takes new events (calendar.create_event)
START_VIEWS = ('auto', 'up_next', 'day', 'week', 'month')
MAX_CALENDARS = 6
MAX_WORDS = 8
AHEAD_DEFAULT, AHEAD_MAX = 14, 31
# Options the app keeps: the screen never needs them (it gets the events already filtered).
# "Status and booking" books on `book_on` (the tile's own calendar unless chosen; "none" books nowhere), with the place
# and the title it names: the app sends them with the events, for a calendar that takes new events.
OWN = ('calendars', 'places', 'words', 'hide_words', 'all_day', 'tentative', 'private', 'ahead', 'book_on', 'book_place', 'book_title')

# The frontend's palette (src/resources/theme/color/color.globals.ts, --color-1 .. --color-54) and the theme colours a
# calendar's colour picker may store by name (src/common/color/compute-color.ts THEME_COLORS).
PALETTE = (
    0x4269D0, 0xF4BD4A, 0xFF725C, 0x6CC5B0, 0xA463F2, 0xFF8AB7, 0x9C6B4E, 0x97BBF5, 0x01AB63, 0x094BAD, 0xC99000, 0xD84F3E,
    0x49A28F, 0x048732, 0xD96895, 0x8043CE, 0x7599D1, 0x7A4C31, 0x6989F4, 0xFFD444, 0xFF957C, 0x8FE9D3, 0x62CC71, 0xFFADDA,
    0xC884FF, 0xBADEFF, 0xBF8B6D, 0x927ACC, 0x97EE3F, 0xBF3947, 0x9F5B00, 0xF48758, 0x8CAED6, 0xF2B94F, 0xEFF26E, 0xE43872,
    0xD9B100, 0x9D7A00, 0x698CFF, 0x00D27E, 0xD06800, 0x009F82, 0xC49200, 0xCBE8FF, 0xFECDDF, 0xC27EB6, 0x8CD2CE, 0xC4B8D9,
    0xF883B0, 0xA49100, 0xF48800, 0x27D0DF, 0xA04A9B, 0x4269D0)
THEME_COLORS = {
    'primary': 0x03A9F4, 'accent': 0xFF9800, 'red': 0xF44336, 'pink': 0xE91E63, 'purple': 0x926BC7, 'deep-purple': 0x6E41AB,
    'indigo': 0x3F51B5, 'blue': 0x2196F3, 'light-blue': 0x03A9F4, 'cyan': 0x00BCD4, 'teal': 0x009688, 'green': 0x4CAF50,
    'light-green': 0x8BC34A, 'lime': 0xCDDC39, 'yellow': 0xFFEB3B, 'amber': 0xFFC107, 'orange': 0xFF9800,
    'deep-orange': 0xFF6F22, 'brown': 0x795548, 'light-grey': 0xBDBDBD, 'grey': 0x9E9E9E, 'dark-grey': 0x606060,
    'blue-grey': 0x607D8B, 'black': 0x000000, 'white': 0xFFFFFF}

# The flags the screen reads (calendar_card.h).
ALL_DAY, TENTATIVE, PRIVATE = 1, 2, 4
# Room for the card's part of the state message: the whole message stays under 4096 bytes (page_delivery.MAX_MESSAGE).
BUDGET = 2600
TITLE_BYTES, PLACE_BYTES, NOTES_BYTES = 48, 32, 160
# A compact event's title and place (the screen asks for the rest on a tap), and what the answer to that tap carries.
# Only the nearest few carry their place (the agenda's rows and up next draw it; the week and the month do not).
SHORT_TITLE, SHORT_PLACE, PLACED = 28, 20, 8
DETAIL_TITLE, DETAIL_PLACE, DETAIL_NOTES = 120, 96, 480
# The screen's feature for compact events and the questions of a tap; the event it asks with, and the op it is answered by.
FEATURE = 'calendar_detail'
EVENT = 'esphome.screen_calendar'
# The events a screen keeps (page_receiver.cpp): 80 with PSRAM, 48 without; a firmware from before `calendar_detail`
# keeps 24 without PSRAM.
KEEPS_PSRAM, KEEPS, KEEPS_BEFORE = 80, 48, 24
# How long fetched events stay fresh; a calendar's own state change fetches again at once (server.Manager).
SECONDS = 120


def calendars_of(tile):
    """The calendars of a card: the tile's own first, then the ones its options add, each once."""
    out = [tile['entity']]
    for entity in (tile.get('options') or {}).get('calendars') or []:
        if isinstance(entity, str) and entity.startswith('calendar.') and entity not in out:
            out.append(entity)
    return out[:MAX_CALENDARS]


def ahead_of(tile):
    value = (tile.get('options') or {}).get('ahead', AHEAD_DEFAULT)
    return value if isinstance(value, int) and 1 <= value <= AHEAD_MAX else AHEAD_DEFAULT


def window(today, ahead):
    """(first day, day after the last) to ask for: from the Monday of this week (the week view shows the days before
    today), through `ahead` days, and the whole month glance: six weeks from the Monday on or before the 1st."""
    first = today.replace(day=1)
    glance = first - timedelta(days=first.weekday())
    start = min(today - timedelta(days=today.weekday()), glance)
    end = max(today + timedelta(days=ahead + 1), glance + timedelta(days=42))
    return start, end


def colour_of(entity, entry, every):
    """Home Assistant's colour for a calendar: its registry's own (a #rrggbb or a theme colour's name), else the palette's
    at its place among all calendars sorted by id, as the frontend's calendar panel picks it."""
    chosen = (((entry or {}).get('options') or {}).get('calendar') or {}).get('color')
    if isinstance(chosen, str):
        text = chosen.strip().lower()
        if text in THEME_COLORS:
            return THEME_COLORS[text]
        if len(text) == 7 and text.startswith('#'):
            try:
                return int(text[1:], 16)
            except ValueError:
                pass
    place = sorted(every).index(entity) if entity in every else 0
    return PALETTE[place % len(PALETTE)]


def moment(value, tz):
    """(datetime in tz, all_day) of Home Assistant's start or end: a date alone is a whole day, a datetime carries its
    own zone (Google keeps the event's), turned into Home Assistant's."""
    if isinstance(value, dict):
        value = value.get('dateTime') or value.get('date')
    if not isinstance(value, str) or not value:
        return None, False
    if len(value) == 10:
        try:
            d = date.fromisoformat(value)
        except ValueError:
            return None, False
        return datetime.combine(d, day_time(0, 0), tzinfo=tz), True
    try:
        moment_ = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None, False
    if moment_.tzinfo is None:
        moment_ = moment_.replace(tzinfo=tz)
    return moment_.astimezone(tz) if tz else moment_, False


def short(text, limit):
    return str(text or '').replace('\n', ' ').strip().encode('utf-8')[:limit].decode('utf-8', errors='ignore')


def cut(text, limit):
    """`text` within `limit` bytes, with an ellipsis where it was cut, so the screen shows that there is more."""
    whole = str(text or '').replace('\n', ' ').strip()
    if len(whole.encode('utf-8')) <= limit:
        return whole
    return short(whole, limit - 3).rstrip() + '…'


def keeps(features, caps):
    """How many events a screen keeps, by its hello: None where its memory is not known (no cap but the budget)."""
    psram = (caps or {}).get('psram_kb')
    if not isinstance(psram, int):
        return None
    if psram > 0:
        return KEEPS_PSRAM
    return KEEPS if FEATURE in (features or ()) else KEEPS_BEFORE


def matches(text, words):
    low = (text or '').lower()
    return any(w.lower() in low for w in words if isinstance(w, str) and w.strip())


def card(tile, fetched, states, entries, tz, now, compact=False, most=None):
    """The `x.cal` of a calendar tile: today, the calendars' colours and names, the events its choices let through as
    minutes from today 00:00, how many did not fit, the notes of the event of the moment (or the next), and a mask a day
    for the month glance. `fetched`: {entity: [Home Assistant's events]}; `entries`: the entity registry by id.
    `compact`: each event's title and place short, and `a` says the screen may ask for the rest (`detail`). `most`: the
    events the screen keeps (`keeps`), the nearest first."""
    options = tile.get('options') or {}
    now = now.astimezone(tz) if tz else now
    today = now.date()
    midnight = datetime.combine(today, day_time(0, 0), tzinfo=now.tzinfo)
    ahead = ahead_of(tile)
    start, end = window(today, ahead)
    calendars = calendars_of(tile)
    every = [e for e in states if e.startswith('calendar.')]
    places = [p for p in options.get('places') or [] if isinstance(p, str) and p.strip()]
    words = [w for w in options.get('words') or [] if isinstance(w, str) and w.strip()]
    hide = [w for w in options.get('hide_words') or [] if isinstance(w, str) and w.strip()]
    show_all_day = options.get('all_day', True) is not False
    show_tentative = options.get('tentative', True) is not False
    private = options.get('private') is True

    def minutes(at):
        return int((at - midnight).total_seconds() // 60)

    rows, glance = [], [0] * 42
    glance_start = today.replace(day=1) - timedelta(days=today.replace(day=1).weekday())
    for index, entity in enumerate(calendars):
        for event in fetched.get(entity) or []:
            if not isinstance(event, dict):
                continue
            found = moments(event, now.tzinfo)
            if not found:
                continue
            begin, finish, all_day = found
            title, place = event.get('summary') or '', event.get('location') or ''
            if places and not matches(place, places):
                continue
            if words and not matches(title, words):
                continue
            if hide and matches(title, hide):
                continue
            if all_day and not show_all_day:
                continue
            tentative = event.get('status') == 'tentative'
            if tentative and not show_tentative:
                continue
            # The month glance: a bit for this calendar on every day the event touches.
            day = max(begin.date(), glance_start)
            while day < finish.date() + timedelta(days=0 if all_day or finish.time() == day_time(0, 0) else 1) and (day - glance_start).days < 42:
                glance[(day - glance_start).days] |= 1 << index
                day += timedelta(days=1)
            flags = (ALL_DAY if all_day else 0) | (TENTATIVE if tentative else 0) | (PRIVATE if private else 0)
            rows.append({'s': minutes(begin), 'e': minutes(finish), 'f': flags, 'c': index,
                         't': '' if private else cut(title, SHORT_TITLE) if compact else short(title, TITLE_BYTES),
                         'p': '' if private else cut(place, SHORT_PLACE) if compact else short(place, PLACE_BYTES),
                         'n': '' if private else short(event.get('description') or '', NOTES_BYTES)})
    rows.sort(key=lambda r: (r['s'], r['e']))
    # The detail list: from the Monday of this week through `ahead` days.
    first_day = -today.weekday()
    every_row = rows
    rows = [r for r in rows if r['e'] > first_day * 1440 and r['s'] < (ahead + 1) * 1440]
    t_now = minutes(now)
    # Nothing on or ahead in those days: the first event after them, so the card says when the next one is ("Next Wed
    # 4 Nov") instead of only that nothing is planned.
    if not any(r['e'] > t_now for r in rows):
        later = [r for r in every_row if r['s'] >= (ahead + 1) * 1440]
        if later:
            rows.append(later[0])
    running = [r for r in rows if not r['f'] & ALL_DAY and r['s'] <= t_now < r['e']]
    coming = [r for r in rows if r['s'] > t_now]
    focus = running[0] if running else coming[0] if coming else None
    names = []
    for entity in calendars:
        attributes = (states.get(entity) or {}).get('attributes') or {}
        names.append([colour_of(entity, entries.get(entity), every), short(attributes.get('friendly_name') or entity, 32)])
    data = {'d': [today.year, today.month, today.day, today.weekday()], 'r': [first_day, ahead], 'c': names,
            'e': [], 'm': 0, 'n': focus['n'] if focus else '',
            'g': [(glance_start - today).days, glance]}
    book = booking(tile, states)
    if book:
        data['b'] = book
    if compact:
        data['a'] = 1
    # Nearest first: the events around now matter most; what does not fit is counted, never silently cut.
    order = sorted(range(len(rows)), key=lambda i: abs(rows[i]['s'] - t_now) if rows[i]['e'] > t_now else 10 ** 9 + t_now - rows[i]['e'])
    kept = set()
    size = len(json.dumps(data, separators=(',', ':')))
    for rank, i in enumerate(order):
        if most is not None and len(kept) >= most:
            break
        r = rows[i]
        if compact and rank >= PLACED:
            r['p'] = ''
        item = [r['s'], r['e'], r['f'], r['c'], r['t'], r['p']]
        cost = len(json.dumps(item, separators=(',', ':'), ensure_ascii=False).encode('utf-8')) + 1
        if size + cost > BUDGET:
            continue
        kept.add(i)
        size += cost
    data['e'] = [[r['s'], r['e'], r['f'], r['c'], r['t'], r['p']] for i, r in enumerate(rows) if i in kept]
    data['m'] = len(rows) - len(kept)
    return data


def moments(event, tz):
    """(begin, finish, all_day) of one of Home Assistant's events as the card counts them, or None without a start."""
    begin, all_day = moment(event.get('start'), tz)
    finish, _ = moment(event.get('end'), tz)
    if not begin:
        return None
    if not finish or finish <= begin:
        finish = begin + (timedelta(days=1) if all_day else timedelta(minutes=1))
    return begin, finish, all_day


def detail(tile, fetched, tz, day, cal, start, end):
    """The answer to a tap on a compact event (op `calendar_event`): its whole title, place and notes, found by its
    calendar's place on the card and its minutes from `day` 00:00 (the day the screen calls today); None when it is gone
    or private."""
    options = tile.get('options') or {}
    calendars = calendars_of(tile)
    if options.get('private') is True or not 0 <= cal < len(calendars):
        return None
    midnight = datetime.combine(day, day_time(0, 0), tzinfo=tz)
    for event in fetched.get(calendars[cal]) or []:
        if not isinstance(event, dict):
            continue
        found = moments(event, tz)
        if not found:
            continue
        begin, finish, _ = found
        if int((begin - midnight).total_seconds() // 60) == start and int((finish - midnight).total_seconds() // 60) == end:
            return {'t': cut(event.get('summary'), DETAIL_TITLE), 'p': cut(event.get('location'), DETAIL_PLACE),
                    'n': cut(event.get('description'), DETAIL_NOTES)}
    return None


def booking(tile, states):
    """[calendar, place, title] a room's card books with, or None: only "Status and booking", only a calendar that takes
    new events (Home Assistant's CREATE_EVENT), the tile's own unless another is chosen."""
    options = tile.get('options') or {}
    if options.get('style') != 'room':
        return None
    entity = options.get('book_on') or tile.get('entity') or ''
    if entity == 'none' or not entity.startswith('calendar.'):
        return None
    features = ((states.get(entity) or {}).get('attributes') or {}).get('supported_features') or 0
    if not isinstance(features, int) or not features & CREATE_EVENT:
        return None
    return [entity, short(options.get('book_place'), BOOK_TEXT), short(options.get('book_title'), BOOK_TEXT)]


def validate(options):
    """The calendar choices of a tile's options, checked and without defaults; ValueError(key) on a wrong one."""
    out = dict(options)
    if 'calendars' in out:
        value = out['calendars']
        if not isinstance(value, list) or len(value) > MAX_CALENDARS - 1 or \
                any(not isinstance(e, str) or not e.startswith('calendar.') or len(e) > 128 for e in value):
            raise ValueError('calendars')
        out['calendars'] = list(dict.fromkeys(value))
        if not out['calendars']:
            del out['calendars']
    for key in ('places', 'words', 'hide_words'):
        if key in out:
            value = out[key]
            if not isinstance(value, list) or len(value) > MAX_WORDS or any(not isinstance(w, str) or len(w) > 48 for w in value):
                raise ValueError(key)
            value = [w.strip() for w in value if w.strip()]
            if value:
                out[key] = list(dict.fromkeys(value))
            else:
                del out[key]
    for key, default in (('all_day', True), ('tentative', True), ('private', False)):
        if key in out:
            if not isinstance(out[key], bool):
                raise ValueError(key)
            if out[key] == default:
                del out[key]
    if 'ahead' in out:
        if not isinstance(out['ahead'], int) or isinstance(out['ahead'], bool) or not 1 <= out['ahead'] <= AHEAD_MAX:
            raise ValueError('ahead')
        if out['ahead'] == AHEAD_DEFAULT:
            del out['ahead']
    if 'style' in out:
        if out['style'] not in STYLES:
            raise ValueError('style')
        if out['style'] == STYLES[0]:
            del out['style']
    if 'soon' in out:
        if not isinstance(out['soon'], int) or isinstance(out['soon'], bool) or not 0 <= out['soon'] <= 120:
            raise ValueError('soon')
        if out['soon'] == 0:
            del out['soon']
    if 'start_view' in out:
        if out['start_view'] not in START_VIEWS:
            raise ValueError('start_view')
        if out['start_view'] == START_VIEWS[0]:
            del out['start_view']
    if 'week_start' in out:
        if out['week_start'] not in WEEK_STARTS:
            raise ValueError('week_start')
        if out['week_start'] == WEEK_STARTS[0]:
            del out['week_start']
    if 'hours' in out:
        value = out['hours']
        if value is None:
            del out['hours']
        elif not isinstance(value, list) or len(value) != 2 or any(not isinstance(h, int) or isinstance(h, bool) for h in value) \
                or not 0 <= value[0] < value[1] <= 24 or value[1] - value[0] < 4:
            raise ValueError('hours')
    if 'week_numbers' in out:
        if not isinstance(out['week_numbers'], bool):
            raise ValueError('week_numbers')
        if not out['week_numbers']:
            del out['week_numbers']
    if 'book_on' in out:
        value = out['book_on']
        if not isinstance(value, str) or len(value) > 128 or (value != 'none' and not value.startswith('calendar.') and value):
            raise ValueError('book_on')
        if not value:
            del out['book_on']
    for key in ('book_place', 'book_title'):
        if key in out:
            if not isinstance(out[key], str) or len(out[key]) > BOOK_TEXT:
                raise ValueError(key)
            out[key] = out[key].strip()
            if not out[key]:
                del out[key]
    return out


KEYS = OWN + ('style', 'soon', 'start_view', 'week_start', 'hours', 'week_numbers')
