"""History on a detail card (app 0.2.59 / firmware 0.2.51): what the manager computes for the screen to draw.

Numbers: 24 time-weighted averages, the highest and lowest moment, an axis in round steps for every kind of unit.
States: a timeline in runs of slots with Home Assistant's words and the time in each state.
"""
from firmware_sources import runtime_source
from manager_fixtures import with_screen_grid
import asyncio
import importlib.util
import json
import re
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles  # noqa: E402
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
sys.path.insert(0, str(ROOT / 'tests'))
import history_card as hc  # noqa: E402

HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None
RUNTIME = runtime_source()

AMSTERDAM = ZoneInfo('Europe/Amsterdam')


def at(text, tz=AMSTERDAM):
    return int(datetime.fromisoformat(text).replace(tzinfo=tz).timestamp())


class Kinds(unittest.TestCase):
    def test_numbers_draw_a_line_and_states_a_timeline(self):
        self.assertEqual(hc.kind('sensor.t', {'state': '21.4', 'attributes': {'unit_of_measurement': '°C'}}), 'line')
        self.assertEqual(hc.kind('sensor.count', {'state': '3', 'attributes': {}}), 'line')
        self.assertEqual(hc.kind('sensor.power', {'state': 'unavailable', 'attributes': {'state_class': 'measurement'}}), 'line')
        self.assertEqual(hc.kind('sensor.washer', {'state': 'running', 'attributes': {}}), 'timeline')
        self.assertEqual(hc.kind('sensor.mode', {'state': '2', 'attributes': {'device_class': 'enum'}}), 'timeline')
        self.assertEqual(hc.kind('sensor.last_seen', {'state': '2026-09-16T10:00:00+00:00', 'attributes': {'device_class': 'timestamp'}}), 'timeline')
        for entity in ('number.target', 'input_number.volume'):
            self.assertEqual(hc.kind(entity, {'state': '5'}), 'line')
        for entity in ('binary_sensor.door', 'switch.kettle', 'input_boolean.guests', 'person.sam'):
            self.assertEqual(hc.kind(entity, {'state': 'on'}), 'timeline')
        for entity in ('light.lamp', 'climate.living', 'cover.blind', 'vacuum.robot'):
            self.assertIsNone(hc.kind(entity, {'state': 'on'}))


class Averages(unittest.TestCase):
    def test_each_part_is_the_time_weighted_mean(self):
        start, end = 0, 24 * 3600
        self.assertEqual(hc.bucket_means([(-100, 20.0)], start, end), [20.0] * 24)
        # 20 for the first half of the fourth hour, 22 for the rest of the day.
        means = hc.bucket_means([(-100, 20.0), (3 * 3600 + 1800, 22.0)], start, end)
        self.assertEqual(means[:3], [20.0] * 3)
        self.assertAlmostEqual(means[3], 21.0)
        self.assertEqual(means[4:], [22.0] * 20)

    def test_unknown_time_does_not_count_and_a_part_without_values_is_none(self):
        start, end = 0, 24 * 3600
        means = hc.bucket_means([(3600, 10.0), (3600 + 900, None), (3600 + 2700, 30.0)], start, end)
        self.assertIsNone(means[0], 'nothing known before the first value')
        self.assertAlmostEqual(means[1], (10 * 900 + 30 * 900) / 1800)
        self.assertEqual(means[2], 30.0)

    def test_statistics_rows_hold_for_their_period_and_gaps_stay_empty(self):
        base = at('2026-09-16T00:00:00')
        # Home Assistant sends milliseconds; the hour from 02:00 has no statistics.
        rows = [{'start': base * 1000, 'mean': 10.0, 'min': 9.0, 'max': 12.0}, {'start': (base + 3600) * 1000, 'mean': 20.0, 'min': 18.0, 'max': 25.0},
                {'start': (base + 3 * 3600) * 1000, 'mean': 30.0, 'min': 29.0, 'max': 31.0}]
        means, extreme = hc.statistic_changes(rows, 3600)
        values = hc.bucket_means(means, base, base + 24 * 3600)
        self.assertEqual(values[:5], [10.0, 20.0, None, 30.0, None], 'the missing hour and the time after the last row stay empty')
        high, low = hc.extremes(extreme, base, base + 24 * 3600)
        self.assertEqual((high, low), ((31.0, base + 10800), (9.0, base)))

    def test_the_highest_and_lowest_moment(self):
        high, low = hc.extremes([(-50, 19.5), (100, 21.2), (200, 18.9), (300, None), (400, 20.0)], 0, 1000)
        self.assertEqual((high, low), ((21.2, 100), (18.9, 200)))
        self.assertEqual(hc.extremes([(-50, 19.5)], 0, 1000), ((19.5, 0), (19.5, 0)), 'a value from before the range counts at its start')
        self.assertEqual(hc.extremes([], 0, 1000), (None, None))


class Axes(unittest.TestCase):
    def labels(self, low, high, unit):
        (bottom, top), ticks = hc.axis(low, high)
        self.assertLessEqual(bottom, low)
        self.assertGreaterEqual(top, high)
        self.assertTrue(all(bottom <= tick <= top for tick in ticks))
        self.assertGreaterEqual(len(ticks), 2)
        self.assertLessEqual(len(ticks), 5)
        return [hc.tick_text(tick, ticks[1] - ticks[0], unit) for tick in ticks]

    def test_round_steps_for_every_kind_of_unit(self):
        self.assertEqual(self.labels(18.97, 21.21, '°C'), ['19°', '20°', '21°'])
        self.assertEqual(self.labels(64.2, 71.9, '°F'), ['65°', '70°'])
        self.assertEqual(self.labels(20.1, 21.4, '°C'), ['20.5°', '21.0°'], 'one number of decimals on the whole axis')
        self.assertEqual(self.labels(35, 62, '%'), ['40%', '50%', '60%'])
        self.assertEqual(self.labels(120, 2450, 'W'), ['1,000', '2,000'])
        self.assertEqual(self.labels(1520.3, 1534.9, 'kWh'), ['1,525', '1,530'])
        self.assertEqual(self.labels(-3.2, 4.1, '°C'), ['-2.5°', '0.0°', '2.5°'])
        self.assertEqual(self.labels(0, 65000, 'lx'), ['0', '25,000', '50,000'])
        self.assertEqual(self.labels(0.0012, 0.0041, 'm³/h'), ['0.002', '0.003', '0.004'])
        self.assertEqual(self.labels(412, 1850, 'ppm'), ['500', '1,000', '1,500'])
        self.assertEqual(self.labels(229.1, 233.4, 'V'), ['230', '232'])

    def test_a_flat_line_gets_room_and_labels(self):
        self.assertEqual(len(self.labels(21.0, 21.0, '°C')), 3)
        self.assertEqual(self.labels(0, 0, ''), ['-1', '0', '1'])

    def test_decimals_follow_the_display_precision(self):
        self.assertEqual(hc.decimals({'options': {'sensor': {'display_precision': 2}}}, [1.0]), 2)
        self.assertEqual(hc.decimals({'options': {'sensor': {'suggested_display_precision': 0}}}, [1.5]), 0)
        self.assertEqual(hc.decimals(None, [3.0, 4.0]), 0)
        self.assertEqual(hc.decimals(None, [3.0, 4.25]), 1)


class Times(unittest.TestCase):
    def test_round_moments_in_the_screen_s_time_zone(self):
        end = at('2026-09-16T16:40:00')
        ticks = hc.time_ticks(end - 24 * 3600, end, 24, AMSTERDAM)
        self.assertEqual([datetime.fromtimestamp(t, AMSTERDAM).strftime('%H:%M') for t in ticks], ['18:00', '00:00', '06:00', '12:00'])
        ticks = hc.time_ticks(end - 3600, end, 1, AMSTERDAM)
        self.assertEqual([datetime.fromtimestamp(t, AMSTERDAM).strftime('%H:%M') for t in ticks], ['15:45', '16:00', '16:15', '16:30'])
        ticks = hc.time_ticks(end - 168 * 3600, end, 168, AMSTERDAM)
        self.assertEqual([datetime.fromtimestamp(t, AMSTERDAM).strftime('%a %H:%M') for t in ticks],
                         ['Thu 00:00', 'Fri 00:00', 'Sat 00:00', 'Sun 00:00', 'Mon 00:00', 'Tue 00:00', 'Wed 00:00'])
        self.assertEqual(hc.utc_offset(end, AMSTERDAM), 7200)

    def test_midnight_stays_midnight_across_daylight_saving(self):
        end = at('2026-10-28T09:00:00')
        ticks = hc.time_ticks(end - 168 * 3600, end, 168, AMSTERDAM)
        self.assertTrue(all(datetime.fromtimestamp(t, AMSTERDAM).strftime('%H:%M') == '00:00' for t in ticks))
        self.assertEqual(hc.utc_offset(end, AMSTERDAM), 3600)


class Messages(unittest.TestCase):
    def test_a_temperature_line(self):
        end = at('2026-09-16T16:40:00')
        start = end - 24 * 3600
        changes = [(start - 600, 20.05)] + [(start + i * 3600 + 1200, 19.0 + (i % 12) * 0.2) for i in range(24)]
        message = hc.line('sensor.living_room_temperature', 24, changes, start, end, AMSTERDAM, None, '°C')
        self.assertEqual((message['op'], message['kind'], message['hours'], message['off'], message['unit']), ('history', 'line', 24, 7200, '°C'))
        self.assertEqual(len(message['values']), 24)
        self.assertEqual(message['yt'][0][1][-1], '°')
        self.assertEqual(message['hi'][0], 21.2)
        self.assertEqual(message['lo'][0], 19.0)
        self.assertLessEqual(message['dom'][0], message['lo'][0])
        self.assertEqual(len(message['xt']), 4)
        self.assertLess(len(json.dumps(message, separators=(',', ':'))), 900)

    def test_a_sensor_two_hours_old_fills_only_its_own_hours(self):
        # Added two hours ago: Home Assistant's history starts at its first state, nothing before it.
        end = at('2026-09-16T16:40:00')
        start = end - 24 * 3600
        changes = [(end - 7200, 480.0), (end - 3600, 510.0), (end - 1800, 530.0)]
        message = hc.line('sensor.new_plug_power', 24, changes, start, end, AMSTERDAM, None, 'W')
        self.assertEqual(message['values'][:22], [None] * 22)
        self.assertEqual(message['values'][22:], [480.0, 520.0])
        self.assertEqual((message['hi'], message['lo']), ([530.0, end - 1800], [480.0, end - 7200]))
        self.assertEqual([text for _, text in message['yt']], ['480', '500', '520'])
        # Statistics with one whole hour compiled so far, and the running hour not yet: that hour and no other.
        rows = [{'start': (end - 5400) // 3600 * 3600 * 1000, 'mean': 495.0, 'min': 480.0, 'max': 510.0}]
        means, extremes = hc.statistic_changes(rows, 3600)
        message = hc.line('sensor.new_plug_power', 24, means, start, end, AMSTERDAM, None, 'W', extremes)
        known = [i for i, value in enumerate(message['values']) if value is not None]
        self.assertEqual(known, [22, 23])
        # A day of a sensor added a minute ago with one state: one value, a flat axis around it.
        message = hc.line('sensor.new_plug_power', 24, [(end - 60, 12.0)], start, end, AMSTERDAM, None, 'W')
        self.assertEqual(sum(value is not None for value in message['values']), 1)
        self.assertLess(message['dom'][0], 12.0)
        self.assertGreater(message['dom'][1], 12.0)

    def test_a_binary_sensor_two_hours_old_shows_no_data_before_it(self):
        end = at('2026-09-16T16:40:00')
        start = end - 24 * 3600
        changes = [(end - 7200, 'off'), (end - 3000, 'on'), (end - 2700, 'off')]
        message = hc.timeline('binary_sensor.new_door', 24, changes, start, end, AMSTERDAM, {'device_class': 'door'})
        self.assertEqual(message['states'], [['Closed', hc.OFF_GREY, 6900], ['Open', 'FFB300', 300]])
        first = message['seg'][0]
        self.assertEqual(first, [0, -1, 0, 79200, 79200], 'no data until the sensor existed')
        self.assertEqual((message['began'], message['active']), (1, 1))

    def test_no_values_sends_an_empty_line(self):
        message = hc.line('sensor.t', 1, [], 0, 3600, timezone.utc)
        self.assertEqual(message['values'], [None] * 24)
        self.assertNotIn('yt', message)

    def test_a_door_timeline_with_home_assistant_s_words(self):
        end = at('2026-09-16T16:40:00')
        start = end - 24 * 3600
        changes = [(start - 3600, 'off'), (start + 3600, 'on'), (start + 3900, 'off'), (start + 7200, 'unavailable'), (start + 7500, 'off'),
                   (start + 36000, 'on'), (start + 36600, 'off')]
        message = hc.timeline('binary_sensor.front_door', 24, changes, start, end, AMSTERDAM, {'device_class': 'door'})
        self.assertEqual([label for label, _, _ in message['states']], ['Closed', 'Open', 'Unavailable'])
        self.assertEqual([color for _, color, _ in message['states']], [hc.OFF_GREY, 'FFB300', hc.NO_DATA])
        self.assertEqual({label: seconds for label, _, seconds in message['states']}, {'Closed': 85200, 'Open': 900, 'Unavailable': 300})
        self.assertEqual(message['began'], 2)
        # The heading follows the door while the card is open: both states in Home Assistant's words.
        self.assertEqual(dict(message['words']), {'off': 'Closed', 'on': 'Open', 'unavailable': 'Unavailable'})
        self.assertEqual(message['seg'][0][:2], [0, 0])
        openings = [run for run in message['seg'] if run[1] == 1]
        self.assertEqual(len(openings), 2, 'both openings show as their own run')
        # A finger reads the real opening, not the 15 minutes of its slot: 01:00 to 01:05 after the start, 5 minutes.
        self.assertEqual(openings[0][2:], [3600, 3900, 300])
        self.assertEqual(openings[1][2:], [36000, 36600, 600])

    def test_people_and_their_zones(self):
        end = 7 * 24 * 3600
        changes = [(-10, 'not_home'), (3600, 'home'), (40000, 'work'), (70000, 'home')]
        message = hc.timeline('person.sam', 168, changes, 0, end, timezone.utc)
        labels = {label: color for label, color, _ in message['states']}
        self.assertEqual(labels, {'Home': '43A047', 'Work': '2196F3', 'Away': hc.OFF_GREY})
        self.assertEqual(message['began'], 2)
        self.assertEqual(dict(message['words']), {'not_home': 'Away', 'home': 'Home', 'work': 'Work'})

    def test_every_zone_gets_its_own_colour(self):
        changes = [(-10, 'home'), (3600, 'not_home'), (4000, 'Office'), (9000, 'not_home'), (9500, 'Gym'), (12000, 'home')]
        message = hc.timeline('person.sam', 24, changes, 0, 24 * 3600, timezone.utc)
        colours = {label: color for label, color, _ in message['states']}
        self.assertEqual((colours['Home'], colours['Away']), ('43A047', hc.OFF_GREY))
        self.assertEqual((colours['Office'], colours['Gym']), (hc.PALETTE[0], hc.PALETTE[1]))

    def test_many_states_join_other_and_the_message_stays_small(self):
        end = 24 * 3600
        states = ['idle', 'washing', 'rinsing', 'spinning', 'drying', 'paused', 'error', 'done']
        changes = [(i * 900, states[i % len(states)]) for i in range(96)]
        message = hc.timeline('sensor.washer', 24, changes, 0, end, timezone.utc, {})
        self.assertEqual(len(message['states']), 6)
        self.assertEqual(message['states'][-1][0], 'Other')
        # Paused, error and done follow each other in every cycle, and share "Other": one run of three slots.
        self.assertEqual(len(message['seg']), 72)
        # "Other" runs read the time of every state it stands for: paused, error and done follow each other.
        other = next(run for run in message['seg'] if run[1] == 5)
        self.assertEqual((other[3] - other[2], other[4]), (2700, 2700))
        self.assertLess(len(json.dumps(message, separators=(',', ':'))), 2500)

    def test_a_busy_motion_sensor_for_a_week_stays_small_and_quick(self):
        # Motion every 30 seconds for a week: 20,160 changes from Home Assistant, still one small message for a CYD.
        import time
        import core
        end = 7 * 24 * 3600
        changes = [(i * 30, 'on' if i % 2 == 0 else 'off') for i in range(end // 30)]
        began = time.monotonic()
        message = hc.timeline('binary_sensor.hallway_motion', 168, changes, 0, end, AMSTERDAM, {'device_class': 'motion'})
        self.assertLess(time.monotonic() - began, 2.0)
        self.assertLessEqual(len(message['seg']), 96)
        self.assertEqual([(label, seconds) for label, _, seconds in message['states']], [('Detected', end // 2), ('Clear', end // 2)])
        self.assertEqual(message['began'], end // 60 - 1, 'the motion already on at the start did not begin in the range')
        self.assertLess(len(core.encode(message).encode()), 1024)

    def test_the_largest_timeline_fits_one_screen_message(self):
        # A week in which the state changes in every slot, with the longest words and many states: still under the
        # 4096 bytes a screen takes.
        import core
        end = 7 * 24 * 3600
        states = [(f'state_{i:02d}_' + 'long_name_' * 3)[:32] for i in range(14)]
        span = end // 96
        changes = []
        for i in range(96):
            # Two states take turns slot by slot; a short third state in each slot fills the legend and the words.
            changes += [(i * span, states[i % 2]), (i * span + span * 8 // 10, states[2 + i % 12]), (i * span + span * 9 // 10, states[i % 2])]
        message = hc.timeline('sensor.status_of_the_washing_machine_in_the_basement', 168, changes, 0, end, AMSTERDAM, {})
        self.assertEqual((len(message['seg']), len(message['states']), len(message['words'])), (96, 6, 10))
        self.assertLessEqual(len(core.encode(message).encode()), 4096)


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class Requests(unittest.IsolatedAsyncioTestCase):
    """A screen's esphome.screen_history event and the one message the manager answers it with."""

    def manager(self, tmp, firmware='0.2.51', extra_tiles=()):
        import test_scaling
        from server import Manager
        ha = test_scaling.fake_ha(firmware=firmware)
        ha.states['binary_sensor.door'] = {'state': 'off', 'attributes': {'device_class': 'door'}}
        ha.states['light.a']['attributes']['brightness'] = 100
        ha.fetches, ha.fail = [], None
        now = datetime.now(timezone.utc).timestamp()

        async def statistic_rows(entity, hours):
            ha.fetches.append(('statistics', entity, hours))
            await asyncio.sleep(0.05)
            if ha.fail:
                raise ha.fail
            first = (now - (hours + 1) * 3600) // 3600 * 3600
            return [{'start': int((first + i * 3600) * 1000), 'mean': 20 + i % 3, 'min': 19, 'max': 23 + i % 2} for i in range(hours)]

        async def state_changes(entity, hours):
            ha.fetches.append(('changes', entity, hours))
            if ha.fail:
                raise ha.fail
            return [(now - hours * 3600, 'off'), (now - 1800, 'on'), (now - 1500, 'off')] if entity == 'binary_sensor.door' else \
                [(now - hours * 3600, '21.0'), (now - 600, '22.5')]
        ha.statistic_rows, ha.state_changes = statistic_rows, state_changes
        m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
        m.save('text.screen', {'title': 'Office 1', 'tiles': [{'entity': 'sensor.t', 'name': ''}, {'entity': 'binary_sensor.door', 'name': ''},
                                                              {'entity': 'light.a', 'name': ''}, *extra_tiles]})
        return m

    async def test_a_number_and_a_door_each_get_one_history_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            await m.answer_history({'inbox': 'text.screen', 'entity': 'sensor.t', 'hours': '24'})
            await m.answer_history({'inbox': 'text.screen', 'entity': 'binary_sensor.door', 'hours': '1'})
            await m.answer_history({'inbox': 'text.screen', 'entity': 'sensor.t', 'hours': '1'})
            sent = [(inbox, message['op'], message['entity'], message['hours'], message['kind'], action) for inbox, message, action in m.ha.messages]
            action = 'esphome.office_1_screen_message'
            self.assertEqual(sent, [('text.screen', 'history', 'sensor.t', 24, 'line', action), ('text.screen', 'history', 'binary_sensor.door', 1, 'timeline', action),
                                    ('text.screen', 'history', 'sensor.t', 1, 'line', action)])
            # A day comes from the hourly statistics, an hour from the exact changes.
            self.assertEqual(m.ha.fetches, [('statistics', 'sensor.t', 24), ('changes', 'binary_sensor.door', 1), ('changes', 'sensor.t', 1)])
            day, door, hour = (message for _, message, _ in m.ha.messages)
            self.assertEqual((day['unit'], len(day['values']), day['hi'][0], day['lo'][0]), ('°C', 24, 24, 19))
            self.assertEqual((door['began'], dict(door['words'])['on']), (1, 'Open'))
            self.assertEqual(hour['values'][-1], 22.5)
            for message in (day, door, hour):
                self.assertLessEqual(len(json.dumps(message, separators=(',', ':'))), 4096)

    async def test_an_energy_source_with_two_sensors_answers_their_sum(self):
        # GitHub #180: two solar arrays open their sum, as Home Assistant's "Power sources" graph adds them up.
        import energy_flow
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, firmware='0.47.0', extra_tiles=[{'entity': 'screen.energy', 'name': '', 'options': {'size': 'square'}}])
            m.ha.states['sensor.roof'] = {'state': '1.5', 'attributes': {'unit_of_measurement': 'kW'}}
            m.ha.states['sensor.shed'] = {'state': '400', 'attributes': {'unit_of_measurement': 'W'}}
            m.forecasts['energy/get_prefs'] = (time.monotonic(), {'energy_sources': [
                {'type': 'solar', 'stat_rate': 'sensor.roof'}, {'type': 'solar', 'stat_rate': 'sensor.shed'}]})
            key = energy_flow.SUMS['solar']
            await m.answer_history({'inbox': 'text.screen', 'entity': key, 'hours': 24})
            await m.answer_history({'inbox': 'text.screen', 'entity': key, 'hours': 1})
            day, hour = (message for _, message, _ in m.ha.messages)
            self.assertEqual((day['entity'], day['kind'], day['unit']), (key, 'line', 'W'))
            # The fake recorder's means are 20..22 per sensor: kW counts a thousandfold.
            self.assertEqual(max(v for v in day['values'] if v is not None), 22 * 1000 + 22)
            self.assertEqual(hour['values'][-1], 22.5 * 1000 + 22.5)
            self.assertEqual(sorted(f[1] for f in m.ha.fetches if f[0] == 'statistics'), ['sensor.roof', 'sensor.shed'])

    async def test_screens_asking_together_share_one_fetch_and_a_reopened_card_uses_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            request = {'inbox': 'text.screen', 'entity': 'sensor.t', 'hours': 168}
            await asyncio.gather(m.answer_history(request), m.answer_history(dict(request)))
            await m.answer_history(dict(request))
            self.assertEqual(m.ha.fetches, [('statistics', 'sensor.t', 168)])
            self.assertEqual(len(m.ha.messages), 3)

    async def test_a_failed_fetch_sends_and_keeps_nothing(self):
        from aiohttp import ClientError
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            m.ha.fail = ClientError('recorder busy')
            with self.assertRaises(ClientError):
                await m.answer_history({'inbox': 'text.screen', 'entity': 'sensor.t', 'hours': 24})
            self.assertEqual((m.ha.messages, m.card_histories), ([], {}))
            m.ha.fail = None
            await m.answer_history({'inbox': 'text.screen', 'entity': 'sensor.t', 'hours': 24})
            self.assertEqual(len(m.ha.messages), 1, 'the card asks again and gets it')

    async def test_what_is_not_answered(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            for request in ({'inbox': 'text.screen', 'entity': 'sensor.co2', 'hours': 24},  # not on this screen
                            {'inbox': 'text.other', 'entity': 'sensor.t', 'hours': 24},
                            {'inbox': 'text.screen', 'entity': 'sensor.t', 'hours': 6},
                            {'inbox': 'text.screen', 'entity': 'sensor.t', 'hours': 'soon'},
                            {'inbox': 'text.screen', 'entity': 'light.a', 'hours': 24},  # a light's card has no history
                            'text.screen'):
                await m.answer_history(request)
            m.ha.states['text.screen'] = {'state': 'unavailable'}
            await m.answer_history({'inbox': 'text.screen', 'entity': 'sensor.t', 'hours': 24})
            self.assertEqual((m.ha.messages, m.ha.fetches), ([], []))

    async def test_the_loop_answers_events_and_survives_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            m.ha.history_requests = asyncio.Queue()
            m.ha.fail = OSError('down')
            loop = asyncio.ensure_future(m.card_history_loop())
            try:
                m.ha.history_requests.put_nowait({'inbox': 'text.screen', 'entity': 'sensor.t', 'hours': '24'})
                await asyncio.sleep(0.2)
                m.ha.fail = None
                m.ha.history_requests.put_nowait({'inbox': 'text.screen', 'entity': 'binary_sensor.door', 'hours': '24'})
                await asyncio.sleep(0.2)
            finally:
                loop.cancel()
            self.assertEqual([message['entity'] for _, message, _ in m.ha.messages], ['binary_sensor.door'])


class Firmware(unittest.TestCase):
    def test_the_screen_asks_with_an_event_and_takes_only_the_answer_it_waits_for(self):
        request = RUNTIME[RUNTIME.index('inline void history_request('):]
        request = request[:request.index('\n}\n')]
        self.assertIn('request.service = esphome::StringRef("esphome.screen_history");', request)
        self.assertIn('request.is_event = true;', request, 'an event needs no permission to call actions')
        self.assertIn('const std::string keys[] = {"inbox", "entity", "hours", "session", "rev", "view"}', request)
        receive = RUNTIME[RUNTIME.index('if (op == "history") {'):]
        receive = receive[:receive.index('#ifdef SWIPE_PROFILE')]
        self.assertIn('if (next.entity != history_asked_entity || next.hours != history_asked_hours) {', receive)
        self.assertIn('if (!valid_entity(next.entity) || (next.hours != 1 && next.hours != 24 && next.hours != 168)) return false;', receive)

    def test_the_card_opens_for_every_entity_with_history_and_keeps_its_range_keys_enabled(self):
        self.assertIn('return d=="sensor"||d=="binary_sensor"||d=="switch"||d=="input_boolean"||d=="person"||d=="number"||d=="input_number";', RUNTIME)
        self.assertIn('if(with_history){\n    render_history_detail(t,large,width,height,pad);', RUNTIME)
        # Range keys ask the manager, not Home Assistant: they are left out of the keys a waiting command disables.
        ranges = RUNTIME[RUNTIME.index('inline void history_ranges('):]
        ranges = ranges[:ranges.index('\n}\n')]
        self.assertIn('if(detail_action_count&&detail_actions[detail_action_count-1]==segment)--detail_action_count;', ranges)
        self.assertIn('if(cmd>=160&&cmd<163){', RUNTIME)
        self.assertLess(RUNTIME.index('if(cmd>=160&&cmd<163){'), RUNTIME.index('if(!(wish_command(cmd)?allowed_wish(esphome::millis(),300+cmd,what):allowed(esphome::millis(),300+cmd,what)))return;'))

    def test_the_scrub_area_keeps_the_finger_and_the_boards_carry_the_small_font(self):
        touch = RUNTIME[RUNTIME.index('inline void history_touch('):]
        touch = touch[:touch.index('\n}\n')]
        for flag in ('lv_obj_add_flag(area,LV_OBJ_FLAG_PRESS_LOCK);', 'lv_obj_remove_flag(area,LV_OBJ_FLAG_GESTURE_BUBBLE);',
                     'lv_obj_add_event_cb(area,history_scrub,LV_EVENT_ALL,nullptr);'):
            self.assertIn(flag, touch)
        for name in ('checkout/guition.yaml', 'checkout/cyd.yaml', 'packages/guition.yaml', 'packages/cyd.yaml'):
            text = profiles.text(name)
            self.assertEqual(len(re.findall(r'runtime_tiles::small_font = id\(sublabel\)->get_lv_font\(\);', text)), 1, name)


if __name__ == '__main__':
    unittest.main()
