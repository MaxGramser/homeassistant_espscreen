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
    used_total = from_grid + solar + from_battery - to_grid - to_battery

    # ... and routing, in its priority order.
    solar_left, grid_left, battery_left = solar, from_grid, from_battery
    to_battery_left, to_grid_left, used_left = to_battery, to_grid, max(used_total, 0.0)
    grid_to_battery = max(0.0, min(to_battery_left, grid_left - used_left))
    to_battery_left -= grid_to_battery
    grid_left -= grid_to_battery
    solar_to_battery = min(solar_left, to_battery_left)
    to_battery_left -= solar_to_battery
    solar_left -= solar_to_battery
    solar_to_grid = min(solar_left, to_grid_left)
    to_grid_left -= solar_to_grid
    solar_left -= solar_to_grid
    battery_to_grid = min(battery_left, to_grid_left)
    battery_left -= battery_to_grid
    more = min(grid_left, to_battery_left)
    grid_to_battery += more
    grid_left -= more
    used_solar = min(used_left, solar_left)
    used_left -= used_solar
    used_battery = min(battery_left, used_left)
    used_left -= used_battery
    used_grid = min(used_left, grid_left)

    m.solar, m.from_grid, m.to_grid, m.from_battery, m.to_battery = solar, from_grid, to_grid, from_battery, to_battery
    m.home = max(0.0, used_total)
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
    return m


def devices(prefs: dict, states: dict[str, dict], home: float) -> list[Device]:
    """The measured devices drawing power now, biggest first.

    Only the top of Home Assistant's device tree: a device `included_in_stat` another one is part of that one's value,
    as in its sankey, and would otherwise be counted twice. A device under 0.1 % of the house is left out, as the
    sankey's threshold does; the card folds what has no place into "Other" itself.
    """
    listed = (prefs or {}).get('device_consumption') or []
    stats = {d.get('stat_consumption') for d in listed}
    out = []
    for order, d in enumerate(listed):
        entity_id = d.get('stat_rate')
        if not entity_id or (d.get('included_in_stat') and d['included_in_stat'] in stats):
            continue
        value = power_w(states.get(entity_id))
        if value is None or value <= 0 or value < home * MIN_DEVICE_SHARE:
            continue
        attributes = (states.get(entity_id) or {}).get('attributes') or {}
        name = d.get('name') or attributes.get('friendly_name') or entity_id
        out.append(Device(entity_id, name, attributes.get('icon') or 'mdi:flash', value, order))
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
    m = moment(prefs, states)
    w = lambda value: round(value, 1) if value > 0 else 0.0  # never -0.0
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
        item = {'n': d.name[:48], 'e': d.entity_id, 'w': w(d.watts), 's': _reading(states.get(d.entity_id))[0],
                'u': _reading(states.get(d.entity_id))[1]}
        code = glyph(d.icon) if glyph else None
        if code:
            item['i'] = code
        devices.append(item)
    if devices:
        out['d'] = devices
    if home_name:
        out['n'] = home_name[:32]
    rest = sum(d.watts for d in m.devices[SENT_DEVICES:])
    if rest > 0:
        out['o'] = w(rest)
    return out
