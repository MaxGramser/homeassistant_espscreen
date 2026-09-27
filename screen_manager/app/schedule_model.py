"""Versioned interval programmes. No HA services, clock or renderer lives here."""
from copy import deepcopy
from datetime import date
import math
import re

VERSION = 1
DAYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
MAX_SLOTS = 16
MAX_PROGRAMMES = 7
STEP_MINUTES = 5


def keys(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise ValueError('Unsupported or missing schedule fields.')


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value):
        raise ValueError('Invalid programme or slot ID.')
    return value


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('A finite numeric value is required.')
    return value


def heating_capabilities(state):
    attrs = (state or {}).get('attributes', {})
    if not {'off', 'heat'} <= set(attrs.get('hvac_modes', [])):
        raise ValueError('This profile requires an on/off heating thermostat.')
    low, high = number(attrs.get('min_temp')), number(attrs.get('max_temp'))
    step = number(attrs.get('target_temp_step', 0.5))
    # v1's UI is Celsius, Off + a positive range capped at the agreed 30 degrees.
    if not 0 < low <= high or not 0 < step <= high - low:
        raise ValueError('Unsupported thermostat temperature range.')
    high = min(high, 30)
    high = round(low + math.floor((high - low) / step + 1e-8) * step, 6)
    if high < low:
        raise ValueError('This thermostat has no supported heating setpoints.')
    return {'profile': 'heating', 'min': low, 'max': high, 'step': step,
            'max_slots': MAX_SLOTS, 'max_programmes': MAX_PROGRAMMES,
            'minute_step': STEP_MINUTES, 'unit': '°C'}


def heating_value(value, capabilities):
    keys(value, ('mode', 'temperature'), ('mode',))
    if value['mode'] == 'off' and set(value) == {'mode'}:
        return {'mode': 'off'}
    if value['mode'] != 'heat' or 'temperature' not in value:
        raise ValueError('Choose Off or a heating temperature.')
    temperature = number(value['temperature'])
    low, high, step = (capabilities[k] for k in ('min', 'max', 'step'))
    n = (temperature - low) / step
    if temperature < low or temperature > high or abs(n - round(n)) > 1e-6:
        raise ValueError('Temperature is outside the thermostat range or step.')
    return {'mode': 'heat', 'temperature': round(temperature, 6)}


def programme(raw, validate_value):
    """Generic geometry/identity validation; a profile owns the typed slot values."""
    keys(raw, ('id', 'name', 'enabled', 'days', 'start_date', 'end_date', 'slots'),
         ('id', 'name', 'enabled', 'days', 'slots'))
    identifier(raw['id'])
    if not isinstance(raw['name'], str) or not 1 <= len(raw['name'].strip()) <= 80:
        raise ValueError('A programme name of at most 80 characters is required.')
    if type(raw['enabled']) is not bool:
        raise ValueError('Programme enabled must be a boolean.')
    days = raw['days']
    if not isinstance(days, list) or not days or any(d not in DAYS for d in days) or len(set(days)) != len(days):
        raise ValueError('Choose at least one distinct weekday.')
    for field in ('start_date', 'end_date'):
        value = raw.get(field)
        if value is not None:
            if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                raise ValueError('Invalid programme date.')
    if raw.get('start_date') and raw.get('end_date') and raw['start_date'] > raw['end_date']:
        raise ValueError('End date precedes start date.')
    slots = raw['slots']
    if not isinstance(slots, list) or not 1 <= len(slots) <= MAX_SLOTS:
        raise ValueError(f'A programme needs 1–{MAX_SLOTS} slots.')
    cursor, ids, result = 0, set(), []
    for slot in slots:
        keys(slot, ('id', 'start', 'end', 'value'), ('id', 'start', 'end', 'value'))
        key = identifier(slot['id'])
        start, end = slot['start'], slot['end']
        if key in ids or type(start) is not int or type(end) is not int:
            raise ValueError('Slots need unique IDs and integer minute boundaries.')
        if start != cursor or end > 1440 or end - start < STEP_MINUTES or start % STEP_MINUTES or end % STEP_MINUTES:
            raise ValueError('Slots must cover the day without gaps, in five-minute steps.')
        ids.add(key)
        cursor = end
        result.append({**slot, 'value': validate_value(slot['value'])})
    if cursor != 1440:
        raise ValueError('The last slot must end at 24:00.')
    return {**deepcopy(raw), 'days': [d for d in DAYS if d in days], 'slots': result,
            'start_date': raw.get('start_date'), 'end_date': raw.get('end_date')}


def no_overlaps(programmes):
    enabled = [p for p in programmes if p['enabled']]
    for i, a in enumerate(enabled):
        for b in enabled[i + 1:]:
            if (set(a['days']) & set(b['days']) and
                    (a.get('start_date') or '0001-01-01') <= (b.get('end_date') or '9999-12-31') and
                    (b.get('start_date') or '0001-01-01') <= (a.get('end_date') or '9999-12-31')):
                raise ValueError('Enabled programmes cannot overlap on the same day.')


def split(slots, index, minute, new_id):
    """Both new intervals keep their value. This is deliberately not event scheduling."""
    result = deepcopy(slots)
    identifier(new_id)
    if len(result) >= MAX_SLOTS or any(s['id'] == new_id for s in result):
        raise ValueError('Slot limit or duplicate ID.')
    old = result[index]
    if type(minute) is not int or minute % STEP_MINUTES or not old['start'] + STEP_MINUTES <= minute <= old['end'] - STEP_MINUTES:
        raise ValueError('The split must leave two slots of at least five minutes.')
    result[index:index + 1] = [{**old, 'end': minute}, {**deepcopy(old), 'id': new_id, 'start': minute}]
    return result


def merge(slots, index):
    """Remove a slot into its preceding neighbour; the first uses the following one."""
    result = deepcopy(slots)
    if len(result) < 2:
        raise ValueError('The last slot cannot be removed.')
    old = result.pop(index)
    if index:
        result[index - 1]['end'] = old['end']
    else:
        result[0]['start'] = old['start']
    return result
