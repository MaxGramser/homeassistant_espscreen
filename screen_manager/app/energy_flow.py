"""The energy card's numbers, the way Home Assistant works them out for its own live view.

Everything here follows Home Assistant's frontend, so the card never asks a person to set anything up:
- what the house has comes from the Energy settings (`energy/get_prefs`): a power sensor (`stat_rate`) per grid
  connection, solar array and battery, the battery's charge (`stat_soc`) and the measured devices
  (`device_consumption`). Home Assistant rewrites inverted and two-sensor setups to one `stat_rate` itself. Before
  2026.3 a grid kept its power sensors in a list of its own (`power`), which the frontend of then added up;
- a power sensor's value in W is `getPowerFromState` (the number, scaled by its unit's SI prefix);
- the split of the moment is `_computePowerData` of hui-power-sankey-card.ts, step for step;
- a device's name is `computeEnergyLabel`: its display name in the Energy settings, else the sensor's name.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# normalize-by-si-prefix.ts: only a unit longer than one character, starting with a known prefix.
SI_PREFIX = {'T': 1e12, 'G': 1e9, 'M': 1e6, 'k': 1e3, 'm': 1e-3, 'µ': 1e-6, 'μ': 1e-6}
# common/sankey.ts MIN_SANKEY_THRESHOLD_FACTOR: a device under 0.1 % of the house is not drawn on its own.
MIN_DEVICE_SHARE = 0.001


def power_w(state: dict | None) -> float | None:
    """A power sensor's value in W, or None when it has no number (getPowerFromState)."""
    if not state:
        return None
    try:
        value = float(state.get('state'))
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN
        return None
    unit = (state.get('attributes') or {}).get('unit_of_measurement') or ''
    if len(unit) > 1 and unit[0] in SI_PREFIX:
        value *= SI_PREFIX[unit[0]]
    return value


@dataclass
class Device:
    entity_id: str
    name: str
    icon: str
    watts: float
    order: int = 0  # its place in the Energy settings, the order Home Assistant shows devices in


@dataclass
class Moment:
    """One moment of the house in W. Flows are named source_to_sink, as the card draws them."""
    has_solar: bool = False
    has_grid: bool = False
    has_battery: bool = False
    solar: float = 0.0
    from_grid: float = 0.0
    to_grid: float = 0.0
    from_battery: float = 0.0
    to_battery: float = 0.0
    home: float = 0.0
    soc: float | None = None
    solar_to_home: float = 0.0
    solar_to_grid: float = 0.0
    solar_to_battery: float = 0.0
    grid_to_home: float = 0.0
    grid_to_battery: float = 0.0
    battery_to_home: float = 0.0
    battery_to_grid: float = 0.0
    # The sensors behind the circles, for a tap that opens one (none for the house: Home Assistant has none either);
    # a source with several sensors names their sum (SUMS).
    solar_entity: str = ''
    grid_entity: str = ''
    battery_entity: str = ''
    devices: list[Device] = field(default_factory=list)
    # The devices under the sankey's threshold, together: Home Assistant groups them as "Other" (common/sankey.ts), so
    # they never count as untracked consumption.
    small: float = 0.0


def rates(source: dict) -> list[str]:
    """A source's power sensors: its `stat_rate`, or on a Home Assistant before 2026.3 (core #162200) a grid's
    `power` list, each entry with a `stat_rate` of its own, as hui-power-sankey-card.ts of that time read them."""
    if source.get('stat_rate'):
        return [source['stat_rate']]
    if source.get('type') == 'grid' and isinstance(source.get('power'), list):
        return [p['stat_rate'] for p in source['power'] if isinstance(p, dict) and p.get('stat_rate')]
    return []


def sources(prefs: dict, kind: str) -> list[dict]:
    return [s for s in (prefs or {}).get('energy_sources') or [] if s.get('type') == kind and rates(s)]


# A source with more than one power sensor (two solar arrays, two grid connections) has no single sensor behind its
# circle. A tap opens what Home Assistant's "Power sources" graph shows for it instead: the sum of all of them
# (power-sources-graph-data.ts). The key travels as a sensor id, which every firmware with the card takes; the add-on
# alone knows it.
SUMS = {'solar': 'sensor.screen_energy_solar_power', 'grid': 'sensor.screen_energy_grid_power',
        'battery': 'sensor.screen_energy_battery_power'}


def source_entity(prefs: dict, kind: str) -> str:
    """The sensor behind a source's circle: its one power sensor, the sum's key for several, '' for none."""
    ids = [e for s in sources(prefs, kind) for e in rates(s)]
    return ids[0] if len(ids) == 1 else SUMS[kind] if ids else ''


def sums(prefs: dict) -> dict[str, list[str]]:
    """The summed sources of this house: key -> the power sensors it adds up."""
    out = {}
    for kind, key in SUMS.items():
        ids = [e for s in sources(prefs, kind) for e in rates(s)]
        if len(ids) > 1:
            out[key] = ids
    return out


def summed_state(states: dict[str, dict], ids: list[str]) -> dict | None:
    """The sum now in W, as a state dict; None when none of the sensors has a number."""
    values = [power_w(states.get(e)) for e in ids]
    values = [v for v in values if v is not None]
    if not values:
        return None
    return {'state': f'{round(sum(values), 1):g}', 'attributes': {'unit_of_measurement': 'W'}}


def scale(state: dict | None) -> float:
    """The factor that turns a sensor's numbers into W (its unit's SI prefix), for its history."""
    unit = ((state or {}).get('attributes') or {}).get('unit_of_measurement') or ''
    return SI_PREFIX[unit[0]] if len(unit) > 1 and unit[0] in SI_PREFIX else 1.0


def summed_changes(series: list[list[tuple[float, float | None]]]) -> list[tuple[float, float | None]]:
    """Several sensors' changes as the changes of their sum: at each moment the sum of what each sensor last said.
    A sensor that has said nothing yet, or has no number, counts as nothing; no sensor with a number gives None."""
    events = sorted((t, i, v) for i, changes in enumerate(series) for t, v in changes)
    last: dict[int, float] = {}
    out = []
    for t, i, v in events:
        if v is None:
            last.pop(i, None)
        else:
            last[i] = v
        out.append((t, sum(last.values()) if last else None))
    return out


def summed_rows(rows: list[list[dict]]) -> list[dict]:
    """Several sensors' statistics rows (already in W) as rows of their sum, period by period, as
    power-sources-graph-data.ts adds up the means that share a moment. Highs and lows of a sum are not the sum of
    highs and lows, so a summed row carries its mean only."""
    by_start: dict[float, float] = {}
    for entity_rows in rows:
        for row in entity_rows:
            mean = row.get('mean')
            if isinstance(row.get('start'), (int, float)) and isinstance(mean, (int, float)):
                by_start[row['start']] = by_start.get(row['start'], 0.0) + mean
    return [{'start': start, 'mean': mean} for start, mean in sorted(by_start.items())]


def related_entities(prefs: dict) -> list[str]:
    """Every entity whose state changes the card: the power sensors, the batteries' charge, the devices."""
    out = []
    for source in (prefs or {}).get('energy_sources') or []:
        for entity_id in rates(source) + ([source['stat_soc']] if source.get('stat_soc') else []):
            if entity_id not in out:
                out.append(entity_id)
    for device in (prefs or {}).get('device_consumption') or []:
        if device.get('stat_rate') and device['stat_rate'] not in out:
            out.append(device['stat_rate'])
    return out


def has_power(prefs: dict) -> bool:
    """Whether Home Assistant can show this house live at all (it hides its own Now view otherwise)."""
    return any(sources(prefs, kind) for kind in ('grid', 'solar', 'battery'))


def route(solar: float, from_grid: float, to_grid: float, from_battery: float, to_battery: float):
    """Where each source's power or energy goes, in Home Assistant's priority order (computeConsumptionSingle in
    data/energy.ts, which _computePowerData of the live view repeats): the excess of the grid over the house into the
    battery first, then solar into the battery, solar to the grid, the battery to the grid, the grid into the battery,
    and what is left to the house from solar, the battery and the grid, in that order. Returns (solar to the house, to
    the grid, to the battery, grid to the house, to the battery, battery to the house, to the grid)."""
    solar, from_grid, to_grid = max(solar, 0.0), max(from_grid, 0.0), max(to_grid, 0.0)
    from_battery, to_battery = max(from_battery, 0.0), max(to_battery, 0.0)
    used_left = max(from_grid + solar + from_battery - to_grid - to_battery, 0.0)
    grid_to_battery = max(0.0, min(to_battery, from_grid - used_left))
    to_battery -= grid_to_battery
    from_grid -= grid_to_battery
    solar_to_battery = min(solar, to_battery)
    to_battery -= solar_to_battery
    solar -= solar_to_battery
    solar_to_grid = min(solar, to_grid)
    to_grid -= solar_to_grid
    solar -= solar_to_grid
    battery_to_grid = min(from_battery, to_grid)
    from_battery -= battery_to_grid
    more = min(from_grid, to_battery)
    grid_to_battery += more
    from_grid -= more
    used_solar = min(used_left, solar)
    used_left -= used_solar
    used_battery = min(from_battery, used_left)
    used_left -= used_battery
    used_grid = min(used_left, from_grid)
    return used_solar, solar_to_grid, solar_to_battery, used_grid, grid_to_battery, used_battery, battery_to_grid


def moment(prefs: dict, states: dict[str, dict]) -> Moment:
    """The house now. `states` maps entity id to a Home Assistant state dict."""
    def watts(entity_id: str) -> float:
        value = power_w(states.get(entity_id))
        return value if value is not None else 0.0

    m = Moment()
    solar_sources, grid_sources, battery_sources = sources(prefs, 'solar'), sources(prefs, 'grid'), sources(prefs, 'battery')
    m.has_solar, m.has_grid, m.has_battery = bool(solar_sources), bool(grid_sources), bool(battery_sources)
    m.solar_entity, m.grid_entity, m.battery_entity = (source_entity(prefs, k) for k in ('solar', 'grid', 'battery'))

    # _computePowerData, collecting: solar only counts when it produces; grids add up per direction; batteries net.
    solar = sum(max(watts(s['stat_rate']), 0.0) for s in solar_sources)
    from_grid = to_grid = 0.0
    for value in (watts(e) for s in grid_sources for e in rates(s)):
        if value > 0:
            from_grid += value
        elif value < 0:
            to_grid += -value
    net_battery = sum(watts(s['stat_rate']) for s in battery_sources)
    from_battery, to_battery = max(net_battery, 0.0), max(-net_battery, 0.0)

    used_solar, solar_to_grid, solar_to_battery, used_grid, grid_to_battery, used_battery, battery_to_grid = route(
        solar, from_grid, to_grid, from_battery, to_battery)

    m.solar, m.from_grid, m.to_grid, m.from_battery, m.to_battery = solar, from_grid, to_grid, from_battery, to_battery
    m.home = max(0.0, from_grid + solar + from_battery - to_grid - to_battery)
    m.solar_to_home, m.solar_to_grid, m.solar_to_battery = used_solar, solar_to_grid, solar_to_battery
    m.grid_to_home, m.grid_to_battery = used_grid, grid_to_battery
    m.battery_to_home, m.battery_to_grid = used_battery, battery_to_grid

    # The charge, as Home Assistant's energy distribution card combines it: each battery's charge weighted by its usable
    # capacity (`capacity`, kWh); a battery without one counts as the mean of those that have one, and with none at all
    # every battery counts the same.
    charged = [(power_w(states.get(s['stat_soc'])), s.get('capacity')) for s in battery_sources if s.get('stat_soc')]
    charged = [(soc, capacity) for soc, capacity in charged if soc is not None]
    known = [c for _, c in charged if isinstance(c, (int, float)) and c > 0]
    mean = sum(known) / len(known) if known else 1.0
    weights = [(soc, c if isinstance(c, (int, float)) and c > 0 else mean) for soc, c in charged]
    m.soc = sum(soc * c for soc, c in weights) / sum(c for _, c in weights) if weights else None

    m.devices = devices(prefs, states, m.home)
    m.small = small_devices(prefs, states, m.home)
    return m


def _live_value(states: dict[str, dict]):
    """A device's power in W for the live view: its power sensor's number, 0 without one (getPowerFromState ?? 0); a
    device without a power sensor has no place in it."""
    return lambda d: (power_w(states.get(d['stat_rate'])) or 0.0) if d.get('stat_rate') else None


def _house_devices(prefs: dict, states: dict[str, dict], home: float, value_of=None):
    """Home Assistant's split of the measured devices for its live view (buildSankeyDeviceNodes in common/sankey.ts):
    the devices drawn straight from the house, as (place in the settings, preference, W), and the power of the small
    ones it groups as "Other" under the house. `value_of` gives a device's value, None where it has none (the live
    view's power by default; a period's energy for hui-energy-sankey-card.ts, which splits its devices the same way).

    A device is drawn when it has a power sensor and reaches 0.1 % of the house. One `included_in_stat` another hangs
    under the first drawn device up its chain and is part of that one's value; with no drawn device above it, it stands
    under the house itself. A small device under the house counts in Other, unless its chain reaches another small
    device first, whose value already holds it. A sensor without a number counts as 0 W (getPowerFromState ?? 0)."""
    listed = [d for d in (prefs or {}).get('device_consumption') or [] if isinstance(d, dict)]
    threshold = home * MIN_DEVICE_SHARE
    by_stat = {d.get('stat_consumption'): d for d in listed if d.get('stat_consumption')}
    value_of = value_of or _live_value(states)
    value = {id(d): v for d in listed for v in [value_of(d)] if v is not None}
    drawn = {d.get('stat_consumption') for d in listed if id(d) in value and value[id(d)] >= threshold}
    small = {d.get('stat_consumption') for d in listed if id(d) in value and id(d) not in drawn and d.get('stat_consumption') not in drawn}

    def under_drawn(device):
        current = device.get('included_in_stat')
        for _ in range(len(listed)):  # a hand-edited chain may run in a circle
            if not current:
                return False
            if current in drawn:
                return True
            above = by_stat.get(current)
            if above is None:
                return False
            current = above.get('included_in_stat')
        return False

    def inside_small(device):
        current = device.get('included_in_stat')
        for _ in range(len(listed)):
            if not current or current in drawn:
                return False
            if current in small:
                return True
            above = by_stat.get(current)
            if above is None:
                return False
            current = above.get('included_in_stat')
        return False

    top, other = [], 0.0
    for order, d in enumerate(listed):
        if id(d) not in value or under_drawn(d):
            continue
        if d.get('stat_consumption') in drawn:
            top.append((order, d, value[id(d)]))
        elif not inside_small(d):
            other += value[id(d)]
    return top, (other if other > 0 else 0.0)


def small_devices(prefs: dict, states: dict[str, dict], home: float) -> float:
    """The power of the small devices under the house, which Home Assistant's sankey shows as "Other"."""
    return _house_devices(prefs, states, home)[1]


def devices(prefs: dict, states: dict[str, dict], home: float) -> list[Device]:
    """The devices Home Assistant's live view draws straight from the house, drawing power now, biggest first.

    A device under another drawn one is part of that one's value and would otherwise be counted twice; the small ones
    are `Moment.small`, "Other" (`_house_devices`). The card folds what has no place into "Other" itself."""
    out = []
    for order, d, watts in _house_devices(prefs, states, home)[0]:
        if watts <= 0:
            continue
        entity_id = d['stat_rate']
        attributes = (states.get(entity_id) or {}).get('attributes') or {}
        name = d.get('name') or attributes.get('friendly_name') or entity_id
        out.append(Device(entity_id, name, attributes.get('icon') or 'mdi:flash', watts, order))
    out.sort(key=lambda dv: -dv.watts)
    return out


# The devices a screen gets by name; what it has no room for it folds into "Other" itself, and the rest of the house's
# devices travel as one number (`o`). Eight is more than the largest card draws (four slots, as power-flow-card-plus).
SENT_DEVICES = 8


def _reading(state: dict | None) -> list[str]:
    """A sensor's own state and unit, as the history card a tap opens shows them."""
    state = state or {}
    unit = (state.get('attributes') or {}).get('unit_of_measurement') or ''
    return [str(state.get('state') or '')[:32], str(unit)[:16]]


def payload(prefs: dict, states: dict[str, dict], glyph=None, home_name: str = '') -> dict:
    """The energy card's `x` on the wire (firmware 0.47.0, page_receiver.cpp): what the house has (`h`), the power of
    each side (`p`), the flows between them (`f`), the batteries' charge (`c`), the sensor behind each source with its
    state (`e`, `u`) and the devices, biggest first (`d`, `o`). `glyph` maps an `mdi:` icon to the codepoint a screen
    draws, or None."""
    return _wire(moment(prefs, states), prefs, states, glyph, home_name)


def _wire(m: Moment, prefs: dict, states: dict[str, dict], glyph=None, home_name: str = '', digits: int = 1) -> dict:
    """A moment as the card's `x`: in W with one decimal for the live view, in kWh with three for a period."""
    w = lambda value: round(value, digits) if value > 0 else 0.0  # never -0.0
    out = {
        'h': (1 if m.has_solar else 0) | (2 if m.has_grid else 0) | (4 if m.has_battery else 0),
        'p': [w(m.solar), w(m.from_grid), w(m.to_grid), w(m.from_battery), w(m.to_battery), w(m.home)],
        'f': [w(m.solar_to_home), w(m.solar_to_grid), w(m.solar_to_battery), w(m.grid_to_home), w(m.grid_to_battery),
              w(m.battery_to_home), w(m.battery_to_grid)],
    }
    if m.soc is not None:
        out['c'] = int(round(min(max(m.soc, 0.0), 100.0)))
    entities = [m.solar_entity, m.grid_entity, m.battery_entity]
    if any(entities):
        summed = sums(prefs)
        out['e'] = entities
        out['u'] = [_reading(summed_state(states, summed[e]) if e in summed else states.get(e)) if e else ['', '']
                    for e in entities]
    # The biggest eight, in the order of the Energy settings: Home Assistant groups the smallest devices and keeps the
    # others where its settings list them, and so does the card with the room it has.
    devices = []
    for d in sorted(m.devices[:SENT_DEVICES], key=lambda dv: dv.order):
        reading = _reading(states.get(d.entity_id)) if d.entity_id else ['', '']
        item = {'n': d.name[:48], 'e': d.entity_id, 'w': w(d.watts), 's': reading[0], 'u': reading[1]}
        code = glyph(d.icon) if glyph else None
        if code:
            item['i'] = code
        devices.append(item)
    if devices:
        out['d'] = devices
    if home_name:
        out['n'] = home_name[:32]
    # Beyond the eight, and the devices under the sankey's threshold: Home Assistant's "Other". What is left of the
    # house after every device is its "Untracked consumption", which the card works out itself.
    rest = sum(d.watts for d in m.devices[SENT_DEVICES:]) + m.small
    if rest > 0:
        out['o'] = w(rest)
    return out


# ---- A period's energy (the tile's `period`, and the full screen's keys): Home Assistant's energy dashboard.
#
# The card shows what Home Assistant's energy distribution and energy sankey cards show for a day, a week, a month or a
# year: how much each source gave and took in kWh, split as data/energy.ts splits it, and each device's use. The add-on
# asks the recorder for the `change` of every energy statistic of the Energy settings (getEnergyData), in kWh (its unit
# conversion), per hour for a day, per day for a week or a month and per month for a year (getSuggestedPeriod), splits
# each of those periods on its own (computeConsumptionData: route() above per timestamp) and adds them up. A device's
# use is the sum of its changes (calculateStatisticSumGrowth), split under the house as the energy sankey card does
# (buildSankeyDeviceNodes, as for power).
PERIODS = ('day', 'week', 'month', 'year')
# The recorder's statistics period for each (getSuggestedPeriod).
STATISTIC_PERIOD = {'day': 'hour', 'week': 'day', 'month': 'day', 'year': 'month'}
# How far back the full screen steps. Home Assistant keeps long-term statistics for ever; the screen stops at about ten
# years, so a finger resting on back never asks for a century.
MAX_BACK = {'day': 3660, 'week': 522, 'month': 120, 'year': 10}


def energy_sources(prefs: dict, kind: str) -> list[dict]:
    """The sources of a kind that measure energy: a grid's import or export, a solar array, a battery."""
    out = []
    for s in (prefs or {}).get('energy_sources') or []:
        if not isinstance(s, dict) or s.get('type') != kind:
            continue
        if s.get('stat_energy_from') or (kind != 'solar' and s.get('stat_energy_to')):
            out.append(s)
    return out


def statistic_ids(prefs: dict) -> list[str]:
    """Every energy statistic the card reads (getReferencedStatisticIds for the grid, solar, batteries and devices)."""
    out = []
    for kind in ('grid', 'solar', 'battery'):
        for s in energy_sources(prefs, kind):
            out += [s.get('stat_energy_from'), s.get('stat_energy_to') if kind != 'solar' else None]
    out += [d.get('stat_consumption') for d in (prefs or {}).get('device_consumption') or [] if isinstance(d, dict)]
    seen = []
    for stat in out:
        if isinstance(stat, str) and stat and stat not in seen:
            seen.append(stat)
    return seen


def has_energy(prefs: dict) -> bool:
    """Whether Home Assistant's energy dashboard has a source to show for this house."""
    return any(energy_sources(prefs, kind) for kind in ('grid', 'solar', 'battery'))


def _changes(stats: dict, ids: list[str]) -> dict[float, float]:
    """The summed change of these statistics per period start (getSummedDataPartial)."""
    out: dict[float, float] = {}
    for stat in ids:
        for row in (stats or {}).get(stat) or []:
            change, start = (row.get('change'), row.get('start')) if isinstance(row, dict) else (None, None)
            if isinstance(change, (int, float)) and isinstance(start, (int, float)):
                out[start] = out.get(start, 0.0) + change
    return out


def growth(stats: dict, stat: str) -> float:
    """A statistic's growth over the period: the sum of its changes (calculateStatisticSumGrowth), 0 without any."""
    return sum(row['change'] for row in (stats or {}).get(stat) or []
               if isinstance(row, dict) and isinstance(row.get('change'), (int, float)))


def period_moment(prefs: dict, stats: dict, states: dict[str, dict]) -> Moment:
    """The house over a period in kWh, from the recorder's `change` rows (statistic id -> rows with `start` and
    `change`): each period split on its own and added up, as Home Assistant's energy dashboard does."""
    m = Moment()
    solar_sources, grid_sources, battery_sources = (energy_sources(prefs, k) for k in ('solar', 'grid', 'battery'))
    m.has_solar, m.has_grid, m.has_battery = bool(solar_sources), bool(grid_sources), bool(battery_sources)
    # A tap on a circle opens its power sensor's history, as on the live card.
    m.solar_entity, m.grid_entity, m.battery_entity = (source_entity(prefs, k) for k in ('solar', 'grid', 'battery'))
    series = {
        'solar': _changes(stats, [s['stat_energy_from'] for s in solar_sources]),
        'from_grid': _changes(stats, [s['stat_energy_from'] for s in grid_sources if s.get('stat_energy_from')]),
        'to_grid': _changes(stats, [s['stat_energy_to'] for s in grid_sources if s.get('stat_energy_to')]),
        'from_battery': _changes(stats, [s['stat_energy_from'] for s in battery_sources if s.get('stat_energy_from')]),
        'to_battery': _changes(stats, [s['stat_energy_to'] for s in battery_sources if s.get('stat_energy_to')]),
    }
    for kind, values in series.items():
        setattr(m, kind, max(0.0, sum(values.values())))
    flows = [0.0] * 7
    home = 0.0
    for start in sorted({t for values in series.values() for t in values}):
        sample = {kind: values.get(start, 0.0) for kind, values in series.items()}
        split = route(sample['solar'], sample['from_grid'], sample['to_grid'], sample['from_battery'], sample['to_battery'])
        flows = [a + b for a, b in zip(flows, split)]
        # used_total of this period (computeConsumptionSingle), never below nothing.
        home += max(0.0, max(sample['from_grid'], 0) + max(sample['solar'], 0) + max(sample['from_battery'], 0)
                    - max(sample['to_grid'], 0) - max(sample['to_battery'], 0))
    (m.solar_to_home, m.solar_to_grid, m.solar_to_battery, m.grid_to_home, m.grid_to_battery, m.battery_to_home,
     m.battery_to_grid) = flows
    m.home = home
    value_of = lambda d: growth(stats, d['stat_consumption']) if d.get('stat_consumption') else None
    top, m.small = _house_devices(prefs, states, m.home, value_of)
    for order, d, kwh in top:
        if kwh <= 0:
            continue
        stat = d['stat_consumption']
        attributes = (states.get(stat) or {}).get('attributes') or {}
        name = d.get('name') or attributes.get('friendly_name') or stat
        # Its power sensor, where it has one, opens on a tap as on the live card; a device measured in energy alone
        # opens nothing.
        m.devices.append(Device(d.get('stat_rate') or '', name, attributes.get('icon') or 'mdi:flash', kwh, order))
    m.devices.sort(key=lambda dv: -dv.watts)
    return m


def period_range(unit: str, offset: int, now, first_day: int = 0):
    """The period `offset` steps from the one `now` is in (0 the one now, -1 the one before), as aware datetimes in
    now's time zone: its first moment and the first moment after it. A week begins on `first_day` (0 Monday .. 6
    Sunday), as Home Assistant's frontend begins it (firstWeekdayIndex)."""
    from datetime import datetime, timedelta
    tz = now.tzinfo
    local = lambda day: datetime(day.year, day.month, day.day, tzinfo=tz)
    if unit == 'day':
        day = now.date() + timedelta(days=offset)
        return local(day), local(day + timedelta(days=1))
    if unit == 'week':
        day = now.date() - timedelta(days=(now.weekday() - first_day) % 7) + timedelta(weeks=offset)
        return local(day), local(day + timedelta(days=7))
    if unit == 'month':
        months = now.year * 12 + now.month - 1 + offset
        return (datetime(months // 12, months % 12 + 1, 1, tzinfo=tz),
                datetime((months + 1) // 12, (months + 1) % 12 + 1, 1, tzinfo=tz))
    return datetime(now.year + offset, 1, 1, tzinfo=tz), datetime(now.year + offset + 1, 1, 1, tzinfo=tz)


# Home Assistant's frontend begins a week on the first day of the user's language: Intl.Locale(language).weekInfo, by
# default (first_weekday "language"). Of the screens' languages, English ("en", the American week) and Portuguese ("pt",
# whose plain form is Brazil's) begin on Sunday; British English and every other one on Monday.
SUNDAY_LANGUAGES = frozenset({'en', 'pt'})


def first_weekday(language: str | None) -> int:
    """0 (Monday) or 6 (Sunday): where a week begins for this language in Home Assistant's frontend."""
    return 6 if (language or 'en') in SUNDAY_LANGUAGES else 0


def period_payload(prefs: dict, stats: dict, states: dict[str, dict], unit: str, start, end, offset: int = 0,
                   glyph=None, home_name: str = '', this_year: int | None = None) -> dict:
    """The card's `x` for a period: the live card's keys in kWh, with the period (`k`), its first and last day (`r`:
    year, month and day of each), how many steps it lies back (`z`, 0 for the period now) and the year now (`y`), so a
    day of another year says its year."""
    from datetime import timedelta
    out = _wire(period_moment(prefs, stats, states), prefs, states, glyph, home_name, digits=3)
    last = end - timedelta(days=1)
    out.update({'k': unit, 'r': [start.year, start.month, start.day, last.year, last.month, last.day], 'z': int(offset),
                'y': this_year or start.year})
    return out
