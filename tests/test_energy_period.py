"""The energy card over a period (its `period`, and the full screen's keys) against Home Assistant's energy dashboard.

The expected values follow data/energy.ts of Home Assistant's frontend: each period's `change` rows split on their own
(computeConsumptionSingle) and added up, a device's use the sum of its changes, and the periods it asks for
(calcDateRange, shiftDateRange, getSuggestedPeriod)."""
import importlib.util
import json
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import energy_flow  # noqa: E402

FIXTURES = ROOT / 'tests/fixtures/energy'
TZ = ZoneInfo('Europe/Amsterdam')
NOW = datetime(2026, 10, 20, 14, 32, tzinfo=TZ)  # a Tuesday


def prefs():
    return json.loads((FIXTURES / 'full-noon.json').read_text())['prefs']


def rows(*changes, start=1_000_000.0):
    """Hourly rows with these changes, in kWh."""
    return [{'start': start + 3600 * i, 'end': start + 3600 * (i + 1), 'change': c} for i, c in enumerate(changes)]


# Two hours: at noon solar fills the battery and the grid, at night the battery and the grid feed the house.
STATS = {
    'sensor.inverter_solar_energy': rows(2.0, 0.0),
    'sensor.p1_meter_energy': rows(0.5, 1.2),
    'sensor.grid_export_energy': rows(1.0, 0.0),
    'sensor.battery_energy': rows(0.0, 0.8),
    'sensor.battery_charged_energy': rows(0.5, 0.0),
    'sensor.wallbox_charging_energy': rows(1.0, 0.5),
    'sensor.heat_pump_energy': rows(0.25, 0.75),
    'sensor.office_energy': rows(0.001, 0.0),
}


class PeriodMoment(unittest.TestCase):
    def test_split_per_period(self):
        m = energy_flow.period_moment(prefs(), STATS, {})
        self.assertTrue(m.has_solar and m.has_grid and m.has_battery)
        self.assertAlmostEqual(m.solar, 2.0)
        self.assertAlmostEqual(m.from_grid, 1.7)
        self.assertAlmostEqual(m.to_grid, 1.0)
        self.assertAlmostEqual(m.from_battery, 0.8)
        self.assertAlmostEqual(m.to_battery, 0.5)
        # Noon: solar 0.5 to the battery, 1 to the grid, 0.5 to the house with 0.5 from the grid. Night: 0.8 from the
        # battery and 1.2 from the grid.
        self.assertAlmostEqual(m.solar_to_battery, 0.5)
        self.assertAlmostEqual(m.solar_to_grid, 1.0)
        self.assertAlmostEqual(m.solar_to_home, 0.5)
        self.assertAlmostEqual(m.grid_to_home, 1.7)
        self.assertAlmostEqual(m.battery_to_home, 0.8)
        self.assertAlmostEqual(m.grid_to_battery, 0.0)
        self.assertAlmostEqual(m.home, 3.0)

    def test_each_period_on_its_own(self):
        # Solar sent out at noon and the grid's energy taken at night are two periods: summed first, the grid's import
        # would be taken for solar used in the house.
        stats = {'sensor.inverter_solar_energy': rows(1.0, 0.0), 'sensor.grid_export_energy': rows(1.0, 0.0),
                 'sensor.p1_meter_energy': rows(0.0, 1.0), 'sensor.battery_energy': rows(0.0, 0.0),
                 'sensor.battery_charged_energy': rows(0.0, 0.0)}
        m = energy_flow.period_moment(prefs(), stats, {})
        self.assertAlmostEqual(m.solar_to_grid, 1.0)
        self.assertAlmostEqual(m.solar_to_home, 0.0)
        self.assertAlmostEqual(m.grid_to_home, 1.0)

    def test_devices(self):
        m = energy_flow.period_moment(prefs(), STATS, {})
        by_name = {d.name: d for d in m.devices}
        self.assertAlmostEqual(by_name['EV'].watts, 1.5)
        self.assertEqual(by_name['EV'].entity_id, 'sensor.wallbox_charging_power')
        self.assertAlmostEqual(by_name['sensor.heat_pump_energy'].watts, 1.0)
        # Under 0.1 % of the house: Home Assistant's Other.
        self.assertNotIn('sensor.office_energy', by_name)
        self.assertAlmostEqual(m.small, 0.001)
        self.assertEqual([d.name for d in m.devices], ['EV', 'sensor.heat_pump_energy'])

    def test_payload(self):
        start, end = energy_flow.period_range('day', 0, NOW)
        x = energy_flow.period_payload(prefs(), STATS, {}, 'day', start, end, 0, home_name='Home')
        self.assertEqual(x['k'], 'day')
        self.assertEqual(x['r'], [2026, 10, 20, 2026, 10, 20])
        self.assertEqual(x['z'], 0)
        self.assertEqual(x['y'], 2026)
        self.assertEqual(x['h'], 7)
        self.assertEqual(x['p'], [2.0, 1.7, 1.0, 0.8, 0.5, 3.0])
        self.assertEqual(x['f'], [0.5, 1.0, 0.5, 1.7, 0.0, 0.8, 0.0])
        self.assertNotIn('c', x)  # a period has no charge
        self.assertEqual(x['o'], 0.001)
        self.assertEqual(x['n'], 'Home')

    def test_nothing_measured(self):
        m = energy_flow.period_moment({'energy_sources': [], 'device_consumption': []}, {}, {})
        self.assertFalse(m.has_solar or m.has_grid or m.has_battery)
        self.assertFalse(energy_flow.has_energy({}))
        self.assertTrue(energy_flow.has_energy(prefs()))

    def test_statistic_ids(self):
        ids = energy_flow.statistic_ids(prefs())
        for stat in ('sensor.p1_meter_energy', 'sensor.grid_export_energy', 'sensor.inverter_solar_energy',
                     'sensor.battery_energy', 'sensor.battery_charged_energy', 'sensor.tv_energy'):
            self.assertIn(stat, ids)
        self.assertEqual(len(ids), len(set(ids)))


class PeriodRange(unittest.TestCase):
    def test_day(self):
        self.assertEqual(energy_flow.period_range('day', 0, NOW), (datetime(2026, 10, 20, tzinfo=TZ), datetime(2026, 10, 21, tzinfo=TZ)))
        self.assertEqual(energy_flow.period_range('day', -1, NOW)[0], datetime(2026, 10, 19, tzinfo=TZ))

    def test_day_of_a_clock_change(self):
        start, end = energy_flow.period_range('day', 5, NOW)  # 25 October 2026: the clocks go back an hour
        self.assertEqual(end.timestamp() - start.timestamp(), 25 * 3600)
        self.assertEqual((start.isoformat(), end.isoformat()), ('2026-10-25T00:00:00+02:00', '2026-10-26T00:00:00+01:00'))

    def test_week(self):
        self.assertEqual(energy_flow.period_range('week', 0, NOW), (datetime(2026, 10, 19, tzinfo=TZ), datetime(2026, 10, 26, tzinfo=TZ)))
        self.assertEqual(energy_flow.period_range('week', 0, NOW, first_day=6)[0], datetime(2026, 10, 18, tzinfo=TZ))
        self.assertEqual(energy_flow.period_range('week', -3, NOW)[0], datetime(2026, 9, 28, tzinfo=TZ))

    def test_month_and_year(self):
        self.assertEqual(energy_flow.period_range('month', 0, NOW), (datetime(2026, 10, 1, tzinfo=TZ), datetime(2026, 11, 1, tzinfo=TZ)))
        self.assertEqual(energy_flow.period_range('month', -10, NOW), (datetime(2025, 12, 1, tzinfo=TZ), datetime(2026, 1, 1, tzinfo=TZ)))
        self.assertEqual(energy_flow.period_range('month', 2, NOW)[0], datetime(2026, 12, 1, tzinfo=TZ))
        self.assertEqual(energy_flow.period_range('year', -1, NOW), (datetime(2025, 1, 1, tzinfo=TZ), datetime(2026, 1, 1, tzinfo=TZ)))

    def test_first_weekday(self):
        # Intl.Locale(language).weekInfo.firstDay, as Home Assistant's frontend reads it.
        self.assertEqual(energy_flow.first_weekday('en'), 6)
        self.assertEqual(energy_flow.first_weekday('en-GB'), 0)
        self.assertEqual(energy_flow.first_weekday('nl'), 0)
        self.assertEqual(energy_flow.first_weekday('pt'), 6)

    def test_statistic_period(self):
        # getSuggestedPeriod: a day by the hour, a week and a month by the day, a year by the month.
        self.assertEqual(energy_flow.STATISTIC_PERIOD, {'day': 'hour', 'week': 'day', 'month': 'day', 'year': 'month'})


HAS_AIOHTTP = importlib.util.find_spec('aiohttp') is not None


@unittest.skipUnless(HAS_AIOHTTP, 'Run using .venv-portal/bin/python for server tests')
class Requests(unittest.IsolatedAsyncioTestCase):
    """A card of a period on a screen: its tile, and the periods its full screen asks for (esphome.screen_energy)."""

    def manager(self, tmp, period='day', tiles=None):
        sys.path.insert(0, str(ROOT / 'tests'))
        import test_scaling
        from manager_fixtures import with_screen_grid
        from server import Manager
        ha = test_scaling.fake_ha(firmware='0.47.0')
        ha.asked = []

        async def energy_changes(ids, start, end, period):
            ha.asked.append((sorted(ids), start, end, period))
            return {stat: rows for stat, rows in STATS.items() if stat in ids}
        ha.energy_changes = energy_changes
        m = Manager(with_screen_grid(ha), Path(tmp) / 'screens.json')
        m.forecasts['energy/get_prefs'] = (time.monotonic(), prefs())
        options = {'size': 'square', **({'period': period} if period else {})}
        m.save('text.screen', {'title': 'Office 1', 'tiles': tiles or [{'entity': 'screen.energy', 'name': '', 'options': options}]})
        return m

    async def test_the_full_screen_gets_the_period_it_asks_for(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            await m.answer_energy({'inbox': 'text.screen', 'unit': 'week', 'offset': '-1'})
            (inbox, message, _), = m.ha.messages
            self.assertEqual((inbox, message['op']), ('text.screen', 'energy'))
            x = message['x']
            self.assertEqual((x['k'], x['z'], x['p'][0]), ('week', -1, 2.0))
            ids, start, end, period = m.ha.asked[0]
            self.assertEqual(period, 'day')
            self.assertEqual(end.timestamp() - start.timestamp(), 7 * 24 * 3600)
            self.assertIn('sensor.p1_meter_energy', ids)
            # Asked again, the same period comes from what the app keeps.
            await m.answer_energy({'inbox': 'text.screen', 'unit': 'week', 'offset': -1})
            self.assertEqual((len(m.ha.messages), len(m.ha.asked)), (2, 1))

    async def test_what_the_full_screen_may_not_ask(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp)
            for request in ({'inbox': 'text.screen', 'unit': 'decade', 'offset': 0},
                            {'inbox': 'text.screen', 'unit': 'day', 'offset': 1},  # tomorrow
                            {'inbox': 'text.screen', 'unit': 'year', 'offset': -11},  # past ten years
                            {'inbox': 'text.screen', 'unit': 'day', 'offset': 'x'},
                            {'inbox': 'text.other', 'unit': 'day', 'offset': 0}, 'nonsense'):
                await m.answer_energy(request)
            self.assertEqual((m.ha.messages, m.ha.asked), ([], []))
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, tiles=[{'entity': 'light.a', 'name': ''}])
            await m.answer_energy({'inbox': 'text.screen', 'unit': 'day', 'offset': 0})
            self.assertEqual(m.ha.messages, [], 'a screen without an energy card asks for nothing')

    async def test_the_tile_waits_for_its_period_then_shows_it(self):
        import core
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, 'month')
            tile = m.layouts['text.screen']['tiles'][0]
            self.assertEqual(tile['options'].get('period'), 'month')
            features = {core.ENERGY_PERIOD_FEATURE}
            message = await m.tile_message(0, tile, features=features, inbox='text.screen')
            self.assertEqual(message['x'], {'k': 'month', 'w': 1})
            self.assertTrue(m.energy_wake.is_set())
            await m.refresh_energy()
            self.assertIn('screen.energy', m.ha.dirty)
            message = await m.tile_message(0, tile, features=features, inbox='text.screen')
            self.assertEqual((message['x']['k'], message['x']['z'], message['x']['p'][5]), ('month', 0, 3.0))
            self.assertEqual(m.ha.asked[0][3], 'day')
            # A period follows the recorder, not every change of power.
            self.assertEqual(tuple(m.related_entities(tile, 'text.screen')), ())
            # A screen whose hello does not say energy_period gets the power now.
            message = await m.tile_message(0, tile, features=set(), inbox='text.screen')
            self.assertNotIn('k', message['x'])

    async def test_the_power_now_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = self.manager(tmp, None)
            tile = m.layouts['text.screen']['tiles'][0]
            self.assertNotIn('period', tile['options'])
            await m.refresh_energy()
            self.assertEqual(m.ha.asked, [])
            self.assertNotEqual(tuple(m.related_entities(tile, 'text.screen')), ())


class Layout(unittest.TestCase):
    def test_the_period_is_the_energy_cards_own(self):
        import core
        self.assertEqual(core.ENERGY_PERIODS, ('now', 'day', 'week', 'month', 'year'))
        self.assertEqual(core.ENERGY_PERIODS[1:], energy_flow.PERIODS)


if __name__ == '__main__':
    unittest.main()
