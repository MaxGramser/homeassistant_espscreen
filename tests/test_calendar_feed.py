"""The calendar card's events (screen_manager/app/calendar_feed.py) against Home Assistant's own rules, on events read
from a real Home Assistant: three local calendars with test events on the bench (tests/fixtures/calendar/bench.json).

Home Assistant's rules: a start without a time is an all-day event whose end does not count; a datetime carries its own
zone; a calendar's colour is its registry's own, else the frontend's palette by its place among all calendars."""
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import calendar_feed as cf  # noqa: E402

DATA = json.loads((ROOT / 'tests/fixtures/calendar/bench.json').read_text())
TZ = ZoneInfo('Europe/Amsterdam')
NOW = datetime(2026, 10, 11, 14, 10, tzinfo=TZ)  # a Sunday, during the Planning session (Work, 13:50 - 15:20)


def card(entity='calendar.work', **options):
    return cf.card({'entity': entity, 'options': options}, DATA['events'], DATA['states'], {}, TZ, NOW)


def titles(data):
    return [row[4] for row in data['e']]


class Card(unittest.TestCase):
    def test_today_and_window(self):
        data = card()
        self.assertEqual(data['d'], [2026, 10, 11, 6])
        # From the Monday of this week through the days ahead.
        self.assertEqual(data['r'], [-6, cf.AHEAD_DEFAULT])

    def test_all_day_spans_whole_days_with_an_exclusive_end(self):
        sprint = next(row for row in card()['e'] if row[4] == 'Sprint week')
        self.assertEqual(sprint[2] & cf.ALL_DAY, cf.ALL_DAY)
        self.assertEqual((sprint[0], sprint[1]), (0, 4 * 1440))  # 11 up to (not including) 15 October

    def test_times_are_minutes_from_today_in_home_assistants_zone(self):
        design = next(row for row in card()['e'] if row[4] == 'Design review')
        self.assertEqual((design[0], design[1]), (13 * 60 + 30, 15 * 60))
        self.assertEqual(design[5], 'Room A')

    def test_minutes_are_wall_clock_across_a_change_of_summer_time(self):
        # The night of 25 October the clocks go back an hour: 09:00 the next morning is still 1440 + 540, as the
        # screen's own clock counts (Python subtracts two times of one zone by their wall clocks).
        now = datetime(2026, 10, 24, 12, 0, tzinfo=TZ)
        events = {'calendar.x': [{'start': '2026-10-25T09:00:00+01:00', 'end': '2026-10-25T10:00:00+01:00', 'summary': 'a'}]}
        data = cf.card({'entity': 'calendar.x', 'options': {}}, events, {'calendar.x': {'attributes': {}}}, {}, TZ, now)
        self.assertEqual(data['e'][0][:2], [1440 + 540, 1440 + 600])

    def test_calendars_of_the_card_and_their_colours(self):
        data = card(calendars=['calendar.family', 'calendar.rooms'])
        names = [name for _, name in data['c']]
        self.assertEqual(names, ['Work', 'Family', 'Rooms'])
        # The palette by place among all calendars sorted by id, as Home Assistant's calendar panel picks it.
        every = sorted(DATA['states'])
        self.assertEqual(data['c'][0][0], cf.PALETTE[every.index('calendar.work')])
        self.assertEqual({row[3] for row in data['e']}, {0, 1, 2})

    def test_registry_colour_wins(self):
        self.assertEqual(cf.colour_of('calendar.work', {'options': {'calendar': {'color': '#123456'}}}, list(DATA['states'])), 0x123456)
        self.assertEqual(cf.colour_of('calendar.work', {'options': {'calendar': {'color': 'red'}}}, list(DATA['states'])), 0xF44336)

    def test_place_filter(self):
        data = card(calendars=['calendar.rooms', 'calendar.family'], places=['room a'])
        self.assertTrue(data['e'])
        self.assertTrue(all(row[5] == 'Room A' for row in data['e']))

    def test_word_filters(self):
        self.assertEqual(set(titles(card(words=['review']))), {'Design review', 'Retainer review'})
        self.assertNotIn('Kick-off call', titles(card(hide_words=['kick-off'])))

    def test_all_day_and_private(self):
        self.assertNotIn('Sprint week', titles(card(all_day=False)))
        data = card(private=True)
        self.assertTrue(all(row[4] == '' and row[5] == '' and row[2] & cf.PRIVATE for row in data['e']))
        self.assertEqual(data['n'], '')

    def test_month_glance_marks_the_days(self):
        data = card(calendars=['calendar.family'])
        start, masks = data['g']
        self.assertEqual(len(masks), 42)
        today = -start
        self.assertTrue(masks[today] & 1 and masks[today] & 2)  # Work and Family both have something today

    def test_budget_counts_what_it_leaves_out(self):
        many = {'calendar.work': [{'start': f'2026-10-{12 + i // 8:02d}T{8 + i % 8:02d}:00:00+02:00',
                                   'end': f'2026-10-{12 + i // 8:02d}T{8 + i % 8:02d}:30:00+02:00',
                                   'summary': 'A rather long meeting title for the budget ' + str(i), 'location': 'Room A'}
                                  for i in range(80)]}
        data = cf.card({'entity': 'calendar.work'}, many, DATA['states'], {}, TZ, NOW)
        self.assertLessEqual(len(json.dumps(data, separators=(',', ':')).encode()), cf.BUDGET + 200)
        self.assertGreater(data['m'], 0)
        self.assertEqual(len(data['e']) + data['m'], 80)


    def test_compact_events_are_short_and_ask_for_the_rest(self):
        long = {'calendar.work': [{'start': '2026-10-11T16:00:00+02:00', 'end': '2026-10-11T17:00:00+02:00',
                                   'summary': 'A rather long meeting title that goes on and on', 'location': 'Conference room on the third floor',
                                   'description': 'Bring the slides'}]}
        data = cf.card({'entity': 'calendar.work'}, long, DATA['states'], {}, TZ, NOW, compact=True)
        row = data['e'][0]
        self.assertEqual(data['a'], 1)
        self.assertTrue(row[4].endswith('…') and len(row[4].encode()) <= cf.SHORT_TITLE)
        self.assertTrue(row[5].endswith('…') and len(row[5].encode()) <= cf.SHORT_PLACE)
        self.assertNotIn('a', cf.card({'entity': 'calendar.work'}, long, DATA['states'], {}, TZ, NOW))
        # A tap asks by the calendar's place and the minutes: the whole event comes back.
        found = cf.detail({'entity': 'calendar.work'}, long, TZ, NOW.date(), row[3], row[0], row[1])
        self.assertEqual(found, {'t': 'A rather long meeting title that goes on and on', 'p': 'Conference room on the third floor', 'n': 'Bring the slides'})
        self.assertIsNone(cf.detail({'entity': 'calendar.work'}, long, TZ, NOW.date(), row[3], row[0] + 1, row[1]))
        self.assertIsNone(cf.detail({'entity': 'calendar.work', 'options': {'private': True}}, long, TZ, NOW.date(), row[3], row[0], row[1]))

    def test_a_busy_week_fits_compact(self):
        # Five events a day over two weeks with long titles and places: whole, the budget ends in a few days; short, the
        # whole of this week and the next fits.
        many = {'calendar.work': [{'start': f'2026-10-{12 + i // 5:02d}T{8 + i % 5 * 2:02d}:00:00+02:00',
                                   'end': f'2026-10-{12 + i // 5:02d}T{9 + i % 5 * 2:02d}:00:00+02:00',
                                   'summary': 'Weekly planning meeting with the whole team ' + str(i), 'location': 'Main office, second floor, room 4'}
                                  for i in range(50)]}
        whole = cf.card({'entity': 'calendar.work'}, many, DATA['states'], {}, TZ, NOW)
        short = cf.card({'entity': 'calendar.work'}, many, DATA['states'], {}, TZ, NOW, compact=True, most=cf.KEEPS)
        self.assertGreater(whole['m'], 20)
        self.assertGreater(len(short['e']), 2 * len(whole['e']) - 5)
        self.assertLessEqual(len(json.dumps(short, separators=(',', ':')).encode()), cf.BUDGET + 200)

    def test_most_keeps_the_nearest_and_counts_the_rest(self):
        many = {'calendar.work': [{'start': f'2026-10-{12 + i // 8:02d}T{8 + i % 8:02d}:00:00+02:00',
                                   'end': f'2026-10-{12 + i // 8:02d}T{8 + i % 8:02d}:30:00+02:00', 'summary': str(i)}
                                  for i in range(40)]}
        data = cf.card({'entity': 'calendar.work'}, many, DATA['states'], {}, TZ, NOW, most=24)
        self.assertEqual(len(data['e']), 24)
        self.assertEqual(data['m'], 16)
        self.assertEqual([row[4] for row in data['e']], [str(i) for i in range(24)])

    def test_what_a_screen_keeps(self):
        self.assertIsNone(cf.keeps({'calendar_detail'}, None))
        self.assertEqual(cf.keeps({'calendar_detail'}, {'psram_kb': 8192}), cf.KEEPS_PSRAM)
        self.assertEqual(cf.keeps({'calendar_detail'}, {'psram_kb': 0}), cf.KEEPS)
        self.assertEqual(cf.keeps(set(), {'psram_kb': 0}), cf.KEEPS_BEFORE)


class Room(unittest.TestCase):
    """ "Status and booking": the calendar a key books on, only one that takes new events (Home Assistant's CREATE_EVENT)."""
    def states(self, features):
        return {**DATA['states'], 'calendar.rooms': {'state': 'off', 'attributes': {'friendly_name': 'Rooms', 'supported_features': features}}}

    def test_books_on_its_own_calendar_with_place_and_title(self):
        tile = {'entity': 'calendar.rooms', 'options': {'style': 'room', 'book_place': 'Room 2', 'book_title': 'Walk-in'}}
        data = cf.card(tile, DATA['events'], self.states(7), {}, TZ, NOW)
        self.assertEqual(data['b'], ['calendar.rooms', 'Room 2', 'Walk-in'])

    def test_no_booking_where_home_assistant_takes_no_events(self):
        tile = {'entity': 'calendar.rooms', 'options': {'style': 'room'}}
        self.assertNotIn('b', cf.card(tile, DATA['events'], self.states(0), {}, TZ, NOW))
        self.assertNotIn('b', cf.card({**tile, 'options': {'style': 'room', 'book_on': 'none'}}, DATA['events'], self.states(1), {}, TZ, NOW))
        self.assertNotIn('b', cf.card({**tile, 'options': {'style': 'busy_free'}}, DATA['events'], self.states(1), {}, TZ, NOW))

    def test_the_next_beyond_the_days_it_looks(self):
        # Nothing in the days the card covers: the first event after them comes along, so the card can say when.
        events = {'calendar.x': [{'start': '2026-11-04T09:00:00+01:00', 'end': '2026-11-04T10:00:00+01:00', 'summary': 'Dentist'}]}
        data = cf.card({'entity': 'calendar.x', 'options': {'ahead': 7}}, events, {'calendar.x': {'attributes': {}}}, {}, TZ, NOW)
        self.assertEqual([row[4] for row in data['e']], ['Dentist'])


class Validate(unittest.TestCase):
    def test_defaults_are_not_stored(self):
        self.assertEqual(cf.validate({'all_day': True, 'tentative': True, 'private': False, 'ahead': 14, 'style': 'events',
                                      'soon': 0, 'start_view': 'auto', 'places': [' ', ''], 'week_start': 'today', 'hours': None,
                                      'week_numbers': False, 'book_on': '', 'book_place': ' ', 'book_title': ''}), {})

    def test_choices(self):
        self.assertEqual(cf.validate({'calendars': ['calendar.a', 'calendar.a'], 'places': [' Room A '], 'soon': 15, 'style': 'busy_free'}),
                         {'calendars': ['calendar.a'], 'places': ['Room A'], 'soon': 15, 'style': 'busy_free'})
        self.assertEqual(cf.validate({'style': 'room', 'week_start': 'monday', 'hours': [8, 18], 'week_numbers': True,
                                      'book_on': 'calendar.rooms', 'book_place': ' Room 2 ', 'book_title': 'Walk-in'}),
                         {'style': 'room', 'week_start': 'monday', 'hours': [8, 18], 'week_numbers': True,
                          'book_on': 'calendar.rooms', 'book_place': 'Room 2', 'book_title': 'Walk-in'})

    def test_refuses(self):
        for options in ({'calendars': ['light.a']}, {'ahead': 0}, {'ahead': 40}, {'soon': 200}, {'style': 'x'},
                        {'start_view': 'year'}, {'all_day': 'yes'}, {'places': 'Room A'}, {'week_start': 'sunday'},
                        {'hours': [18, 8]}, {'hours': [8, 10]}, {'hours': [8, 25]}, {'hours': '8-18'}, {'week_numbers': 'yes'},
                        {'book_on': 'light.a'}, {'book_title': 'x' * 49}):
            with self.assertRaises(ValueError):
                cf.validate(options)


if __name__ == '__main__':
    unittest.main()
