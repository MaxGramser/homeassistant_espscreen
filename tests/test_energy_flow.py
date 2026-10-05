"""The energy card's numbers against Home Assistant's own rules, on moments read from a real Home Assistant.

The fixtures are energy/get_prefs and the states of the sensors they name, read from the bench Home Assistant with a
fake house wired into its Energy settings (tests/fixtures/energy/*.json). The expected values are what Home Assistant's
frontend computes for its own live view (hui-power-sankey-card.ts _computePowerData)."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'screen_manager/app'))
import energy_flow  # noqa: E402

FIXTURES = ROOT / 'tests/fixtures/energy'


def load(key):
    data = json.loads((FIXTURES / f'{key}.json').read_text())
    return data['prefs'], data['states']


class PowerFromState(unittest.TestCase):
    def test_si_prefix(self):
        self.assertEqual(energy_flow.power_w({'state': '2.4', 'attributes': {'unit_of_measurement': 'kW'}}), 2400)
        self.assertEqual(energy_flow.power_w({'state': '1200', 'attributes': {'unit_of_measurement': 'W'}}), 1200)
        self.assertAlmostEqual(energy_flow.power_w({'state': '500', 'attributes': {'unit_of_measurement': 'mW'}}), 0.5)

    def test_no_number(self):
        for state in ('unavailable', 'unknown', '', 'nan'):
            self.assertIsNone(energy_flow.power_w({'state': state, 'attributes': {}}))
        self.assertIsNone(energy_flow.power_w(None))


class Split(unittest.TestCase):
    def check(self, key, **expected):
        m = energy_flow.moment(*load(key))
        for name, value in expected.items():
            self.assertAlmostEqual(getattr(m, name), value, places=3, msg=f'{key}: {name}')
        return m

    def test_noon_solar_charges_and_exports(self):
        m = self.check('full-noon', solar=5200, to_grid=1200, to_battery=1500, home=2500,
                       solar_to_home=2500, solar_to_grid=1200, solar_to_battery=1500, grid_to_home=0, soc=64)
        self.assertTrue(m.has_solar and m.has_grid and m.has_battery)

    def test_evening_battery_and_grid(self):
        self.check('full-evening', home=2550, battery_to_home=2100, grid_to_home=450, solar_to_home=0)

    def test_cheap_night_grid_charges_the_battery(self):
        self.check('full-cheap_night', home=800, grid_to_battery=3000, grid_to_home=800)

    def test_battery_sells_to_the_grid(self):
        self.check('full-sell_peak', home=800, battery_to_home=800, battery_to_grid=3200)

    def test_nothing_flows(self):
        self.check('full-quiet', home=0, grid_to_home=0, solar_to_home=0, battery_to_home=0)

    def test_solar_without_battery(self):
        m = self.check('solar-solar_noon', home=900, solar_to_home=900, solar_to_grid=2200)
        self.assertFalse(m.has_battery)
        self.assertIsNone(m.soc)

    def test_grid_only(self):
        m = self.check('grid-flat_evening', home=640, grid_to_home=640)
        self.assertFalse(m.has_solar or m.has_battery)

    def test_two_arrays_two_sensor_grid_inverted_battery(self):
        # Home Assistant turns the two grid sensors and the inverted battery sensor into one stat_rate each, and one
        # array reports kW: 3.1 kW + 2.4 kW of sun.
        self.check('odd-two_arrays', solar=5500, to_grid=2900, to_battery=900, home=1700,
                   solar_to_home=1700, solar_to_grid=2900, solar_to_battery=900)


class Devices(unittest.TestCase):
    def test_biggest_first_names_and_icons_from_home_assistant(self):
        m = energy_flow.moment(*load('full-busy'))
        self.assertEqual([d.watts for d in m.devices], sorted((d.watts for d in m.devices), reverse=True))
        self.assertEqual(m.devices[0].name, 'EV')  # the display name in the Energy settings
        self.assertEqual(m.devices[0].icon, 'mdi:car-electric')
        self.assertIn('Heat Pump Power', [d.name for d in m.devices])  # else the sensor's own name
        self.assertEqual(len(m.devices), 7)  # the office draws nothing

    def test_nested_devices_are_not_counted_twice(self):
        prefs, states = load('full-busy')
        prefs = json.loads(json.dumps(prefs))
        dishwasher = next(d for d in prefs['device_consumption'] if 'dishwasher' in d['stat_rate'])
        dishwasher['included_in_stat'] = next(d for d in prefs['device_consumption'] if 'oven' in d['stat_rate'])['stat_consumption']
        names = [d.name for d in energy_flow.moment(prefs, states).devices]
        self.assertNotIn('Dishwasher Power', names)

    def test_related_entities(self):
        prefs, _ = load('full-noon')
        related = energy_flow.related_entities(prefs)
        self.assertIn('sensor.p1_meter_power', related)
        self.assertIn('sensor.battery_state_of_charge', related)
        self.assertIn('sensor.heat_pump_power', related)
        self.assertTrue(energy_flow.has_power(prefs))
        self.assertFalse(energy_flow.has_power({'energy_sources': [{'type': 'grid', 'stat_energy_from': 'x'}]}))


if __name__ == '__main__':
    unittest.main()


class Wire(unittest.TestCase):
    """What a screen gets (energy_flow.payload), in the form page_receiver.cpp reads."""
    def test_busy_house(self):
        prefs, states = load('full-busy')
        x = energy_flow.payload(prefs, states, lambda icon: 'F0B6C' if icon == 'mdi:car-electric' else None)
        m = energy_flow.moment(prefs, states)
        self.assertEqual(x['h'], 7)
        self.assertEqual(len(x['p']), 6)
        self.assertEqual(len(x['f']), 7)
        self.assertAlmostEqual(x['p'][5], round(m.home, 1))
        # The biggest eight at most, in the order of the Energy settings as Home Assistant shows them, the rest as one
        # number; each with the sensor's own state and unit.
        listed = [d['stat_rate'] for d in prefs['device_consumption']]
        order = [listed.index(d['e']) for d in x['d']]
        self.assertEqual(order, sorted(order))
        self.assertLessEqual(len(x['d']), energy_flow.SENT_DEVICES)
        for d in x['d']:
            self.assertEqual(d['s'], states[d['e']]['state'])
            self.assertTrue(d['n'])
        self.assertEqual(len(x['u']), 3)
        self.assertEqual(x['u'][1][0], states[x['e'][1]]['state'])

    def test_no_settings(self):
        x = energy_flow.payload({}, {})
        self.assertEqual(x['h'], 0)
        self.assertNotIn('d', x)
        self.assertNotIn('e', x)

    def test_fits_a_message(self):
        # Eight devices with long names and every sensor stays far below what a state message may carry.
        prefs, states = load('full-busy')
        x = energy_flow.payload(prefs, states)
        self.assertLess(len(json.dumps(x, separators=(',', ':'))), 1500)


class EditorParity(unittest.TestCase):
    """The editor offers the energy card where the firmware draws its diagram: the same least room in both."""
    def test_least_room(self):
        import re
        firmware = (ROOT / 'components/smart_display/energy_card.h').read_text()
        editor = (ROOT / 'web/src/model/ui-scale.ts').read_text()
        found = dict(re.findall(r'(MIN_\w+_MM\w*) = (\d+)', firmware))
        ts = re.search(r'ENERGY_MIN_MM = \{ width: (\d+), compact: (\d+), standard: (\d+) \}', editor)
        self.assertIsNotNone(ts)
        self.assertEqual((found['MIN_WIDTH_MM'], found['MIN_HEIGHT_MM_COMPACT'], found['MIN_HEIGHT_MM_STANDARD']), ts.groups())


class Layout(unittest.TestCase):
    """The energy card in a layout: a card of the screen's own, for firmware 0.47.0 and newer, with no face of its own."""
    def test_gate_and_options(self):
        import core
        layout = core.validate_layout({'title': 'House', 'tiles': [
            {'entity': 'screen.energy', 'name': '', 'options': {'size': 'square', 'display': 'standard', 'sub': 'none'}}]})
        self.assertEqual(core.min_firmware(layout), core.ENERGY_MIN_FIRMWARE)
        self.assertEqual(layout['tiles'][0]['options'], {'size': 'square'})
        self.assertEqual(core.builtin_name('screen.energy', core.english), 'Energy')

    def test_message_carries_the_house(self):
        import core
        prefs, states = load('full-noon')
        tile = {'entity': 'screen.energy', 'name': '', 'options': {'size': 'square'}}
        message = core.state_message(0, tile, states, core.extras(tile, states, energy=prefs))
        self.assertEqual(message['x']['h'], 7)
        self.assertEqual(message['name'], 'Energy')


class Charge(unittest.TestCase):
    """The batteries' charge as Home Assistant's distribution card combines it: weighted by usable capacity."""
    def prefs(self, *capacities):
        return {'energy_sources': [{'type': 'battery', 'stat_rate': f'sensor.b{i}_power', 'stat_soc': f'sensor.b{i}_soc',
                                    **({'capacity': c} if c is not None else {})} for i, c in enumerate(capacities)]}

    def states(self, *socs):
        return {f'sensor.b{i}_soc': {'state': str(v), 'attributes': {'unit_of_measurement': '%'}} for i, v in enumerate(socs)}

    def test_weighted(self):
        self.assertAlmostEqual(energy_flow.moment(self.prefs(10, 5), self.states(90, 30)).soc, 70)

    def test_without_capacity_the_mean(self):
        self.assertAlmostEqual(energy_flow.moment(self.prefs(10, None), self.states(90, 30)).soc, 60)
        self.assertAlmostEqual(energy_flow.moment(self.prefs(None, None), self.states(90, 30)).soc, 60)

    def test_home_name(self):
        x = energy_flow.payload(self.prefs(None), self.states(50), home_name='Our house')
        self.assertEqual(x['n'], 'Our house')
