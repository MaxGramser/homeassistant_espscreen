"""Native HA Schedule adapter. HA owns persistence and the clock, not the panel."""
import asyncio
from copy import deepcopy
import hashlib
import json
import re

import heating_package
import schedule_model as model

WEEKDAYS = dict(zip(model.DAYS, ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')))


class Conflict(ValueError):
    pass


class Unavailable(ConnectionError):
    pass


class PartialSave(ConnectionError):
    pass


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()[:24]


def minute(value, end=False):
    if end and value in ('24:00', '24:00:00'):
        return 1440
    if not isinstance(value, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d(?::00)?', value):
        raise ValueError('Only whole-minute times can be edited here.')
    return int(value[:2]) * 60 + int(value[3:5])


def clock(value):
    return f'{value // 60:02d}:{value % 60:02d}:00'


def blank(binding, kind):
    label = 'ESP Screen heating: ' if kind == 'weekly' else 'ESP Screen Vacation: '
    return {'id': binding[kind].split('.')[1], 'name': label + binding['entity'].split('.')[1].replace('_', ' '),
            'icon': 'mdi:calendar-clock', **{day: [] for day in WEEKDAYS.values()}}


def block_value(data, binding, caps):
    """Interpret HA data without requiring editor-specific IDs or grouping tags."""
    model.keys(data, ('esp_screen', 'programme', 'name', 'enabled', 'slot', 'mode', 'temperature'))
    if 'esp_screen' in data and data['esp_screen'] != binding['key']:
        raise ValueError('This helper contains data belonging to another controller.')
    if 'enabled' in data and type(data['enabled']) is not bool:
        raise ValueError('Block enabled must be a boolean.')
    mode = data.get('mode')
    if mode not in (None, 'off', 'heat'):
        raise ValueError('Choose Off or a heating temperature.')
    if data.get('enabled') is False or mode == 'off':
        return {'mode': 'off'}
    if 'temperature' not in data:
        if mode == 'heat':
            raise ValueError('A heating block needs a temperature.')
        return {'mode': 'off'}
    temperature = model.number(data['temperature'])
    return {'mode': 'off'} if temperature == 0 else model.heating_value(
        {'mode': 'heat', 'temperature': temperature}, caps)


def decode_day(blocks, day, binding, caps):
    if not isinstance(blocks, list):
        raise ValueError('A weekday must contain a list of time blocks.')
    if not blocks:
        return None
    intervals = []
    for block in blocks:
        model.keys(block, ('from', 'to', 'data'), ('from', 'to'))
        intervals.append((minute(block['from']), minute(block['to'], end=True),
                          block_value(block.get('data', {}), binding, caps)))
    slots, cursor = [], 0
    def append(start, end, value):
        slots.append({'id': f'ha_{start}_{end}', 'start': start, 'end': end, 'value': value})
    for start, end, value in sorted(intervals, key=lambda interval: interval[0]):
        if start < cursor or end <= start:
            raise ValueError('Time blocks must not overlap or end before they start.')
        if start > cursor:
            append(cursor, start, {'mode': 'off'})
        append(start, end, value)
        cursor = end
    if cursor < 1440:
        append(cursor, 1440, {'mode': 'off'})
    return model.programme({'id': 'ha_' + day, 'name': 'Heating schedule: ' + day,
                            'enabled': True, 'days': [day], 'slots': slots},
                           lambda v: model.heating_value(v, caps))


def decode(row, binding, caps):
    model.keys(row, ('id', 'name', 'icon', *WEEKDAYS.values()), ('id', 'name'))
    programmes = []
    for day, field in WEEKDAYS.items():
        p = decode_day(row.get(field, []), day, binding, caps)
        if p is None:
            continue
        # Group identical presentations only; HA's days remain independent.
        # Old programme/slot metadata never couples their future edits.
        existing = next((old for old in programmes if old['slots'] == p['slots']), None)
        if existing:
            existing['days'].append(day)
        else:
            programmes.append(p)
    return programmes


def encode_native(p, previous, binding, caps):
    """Preserve unchanged HA blocks and gaps; new blocks need only temperature."""
    result, gaps, cursor = [], set(), 0
    for block in sorted(previous, key=lambda block: minute(block['from'])):
        start, end = minute(block['from']), minute(block['to'], end=True)
        if start > cursor:
            gaps.add((cursor, start))
        cursor = end
    if cursor < 1440:
        gaps.add((cursor, 1440))
    for slot in p['slots']:
        value = slot['value'] if p['enabled'] else {'mode': 'off'}
        old = next((block for block in previous
                    if minute(block['from']) == slot['start'] and minute(block['to'], end=True) == slot['end']
                    and block_value(block.get('data', {}), binding, caps) == value), None)
        if old is not None:
            result.append(deepcopy(old))
        elif not p['enabled']:
            result.append({'from': clock(slot['start']), 'to': clock(slot['end']),
                           'data': {**slot['value'], 'enabled': False}})
        elif value['mode'] != 'off' or (slot['start'], slot['end']) not in gaps:
            result.append({'from': clock(slot['start']), 'to': clock(slot['end']),
                           'data': {'temperature': value.get('temperature', 0)}})
        # Keep an unchanged native gap empty, including an entirely empty day.
    return result


class Adapter:
    def __init__(self, backend, states, units):
        self.backend, self.states, self.units = backend, states, units
        self._lock = asyncio.Lock()

    def capabilities(self, entity):
        heating_package.binding(entity)
        if self.units().get('temperature') != '°C':
            raise ValueError('The first heating profile requires Celsius.')
        return model.heating_capabilities(self.states().get(entity))

    async def snapshot(self, entity):
        b, caps = heating_package.binding(entity), self.capabilities(entity)
        rows = await self.backend('schedule/list')
        if not isinstance(rows, list) or any(not isinstance(r, dict) or not isinstance(r.get('id'), str) for r in rows):
            raise Unavailable('Unsupported native Schedule API response.')
        owned, programmes, readonly, vacation_programme = {}, [], [], None
        for kind in ('weekly', 'vacation_schedule'):
            row = next((r for r in rows if r['id'] == b[kind].split('.')[1]), None)
            if row is None:
                continue
            owned[kind] = row
            try:
                values = decode(row, b, caps)
                if kind == 'weekly':
                    programmes = values
                elif values:
                    if len(values) != 1 or values[0]['days'] != list(model.DAYS) or not values[0]['enabled']:
                        raise ValueError('Vacation needs one enabled timeline repeated on all seven days.')
                    vacation_programme = values[0]
            except (ValueError, TypeError, KeyError) as error:
                readonly.append({'schedule_id': row['id'], 'name': row.get('name'), 'reason': str(error)})
        states = self.states()
        override = states.get(b['vacation'], {}).get('state')
        ready = (states.get(b['service'], {}).get('state') in ('on', 'off') and
                 states.get(b['reconcile'], {}).get('state') == 'on' and override in ('on', 'off') and
                 states.get(b['service'], {}).get('attributes', {}).get('esp_screen_controller') == heating_package.CONTROLLER_VERSION)
        # Active slot/next_event changes are deliberately absent from revisions.
        revision = fingerprint({'schedules': owned, 'vacation': override, 'capabilities': caps})
        return {'v': model.VERSION, 'entity': entity, 'backend': 'home_assistant_schedule', 'binding': b,
                'revision': revision, 'capabilities': {**caps, 'vacation': ready}, 'controller_ready': ready,
                'programmes': programmes, 'readonly': readonly,
                'warnings': [f"{r['name']}: {r['reason']}" for r in readonly],
                'vacation': {'enabled': override == 'on', 'value': vacation_programme['slots'][0]['value'] if vacation_programme else {'mode': 'off'}},
                'vacation_programme': vacation_programme, 'vacation_timeline_ready': ready}, owned

    async def load(self, entity):
        return (await self.snapshot(entity))[0]

    @staticmethod
    def check(before, revision):
        if revision != before['revision']:
            raise Conflict('The schedule changed in Home Assistant. Reload before saving.')
        if not before['controller_ready']:
            raise Unavailable('Install or update the native heating controller package in Home Assistant before saving.')
        if before['readonly']:
            raise ValueError('Unsupported managed helper data is read-only; resolve it in Home Assistant.')

    async def hide(self, binding):
        registry = await self.backend('config/entity_registry/list')
        for field in ('weekly', 'vacation_schedule', 'vacation', 'service', 'reconcile'):
            entry = next((r for r in registry if r['entity_id'] == binding[field]), None)
            if entry and not entry.get('hidden_by'):
                await self.backend('config/entity_registry/update', entity_id=entry['entity_id'], hidden_by='user')

    async def ensure(self, binding, rows):
        """A write/setup operation; loading the panel never creates helpers."""
        created_any = False
        for kind in ('weekly', 'vacation_schedule'):
            if kind not in rows:
                row = blank(binding, kind)
                # HA derives the immutable storage ID from the initial name.
                # Assign a readable name immediately afterwards; entity IDs stay stable.
                created = await self.backend('schedule/create', **{k: v for k, v in row.items() if k not in ('id', 'name')}, name=row['id'])
                if created.get('id') != row['id']:
                    raise PartialSave('Helper identity conflict. Inspect the newly created helper before retrying.')
                await self.backend('schedule/update', schedule_id=row['id'], **{k: v for k, v in row.items() if k != 'id'})
                confirmed = await self.backend('schedule/list')
                if next((r for r in confirmed if r['id'] == row['id']), None) != row:
                    raise PartialSave('Home Assistant has not confirmed the new helper. Reload before retrying.')
                rows[kind] = row
                created_any = True
        if created_any:
            await self.hide(binding)

    async def write(self, entity, before, rows, kind, p, day=None):
        try:
            await self.ensure(before['binding'], rows)
            # Helper creation / registry calls await HA. Recheck after those awaits
            # so an intervening external edit is not overwritten by our old copy.
            current, fresh = await self.snapshot(entity)
            if (current['vacation']['enabled'] != before['vacation']['enabled'] or
                    current['capabilities'] != before['capabilities'] or
                    any(fresh.get(k) != row for k, row in rows.items())):
                raise Conflict('The schedule changed in Home Assistant. Reload before saving.')
            self.check(current, current['revision'])
            row = deepcopy(rows[kind])
            encode_day = lambda d: encode_native(p, row[WEEKDAYS[d]], before['binding'], before['capabilities'])
            if day:
                row[WEEKDAYS[day]] = encode_day(day)
            else:
                old = next((old for old in before['programmes'] if old['id'] == p['id']), None) if kind == 'weekly' else None
                for d, field in WEEKDAYS.items():
                    if d in p['days']:
                        row[field] = encode_day(d)
                    elif old and d in old['days']:
                        row[field] = []
            await self.backend('schedule/update', schedule_id=row['id'], **{k: v for k, v in row.items() if k != 'id'})
            _, current = await self.snapshot(entity)
            if current.get(kind) != row:
                raise PartialSave('Home Assistant has not confirmed the saved schedule.')
            await self.backend('call_service', domain='script', service=before['binding']['service'].split('.')[1], service_data={})
            return await self.load(entity)
        except Conflict:
            raise
        except (ConnectionError, TimeoutError, ValueError) as error:
            raise PartialSave('Save was not fully confirmed. Reload before retrying; some changes may be saved.') from error

    async def save(self, entity, revision, draft):
        async with self._lock:
            before, rows = await self.snapshot(entity)
            self.check(before, revision)
            p = model.programme(draft, lambda v: model.heating_value(v, before['capabilities']))
            if p.get('start_date') or p.get('end_date'):
                raise ValueError('Native Schedule helpers support weekly programmes, not dated events.')
            others = [old for old in before['programmes'] if old['id'] != p['id']]
            if any(set(old['days']) & set(p['days']) for old in others):
                raise ValueError('This programme would replace another programme; edit a weekday instead.')
            return await self.write(entity, before, rows, 'weekly', p)

    async def save_day(self, entity, revision, day, slots):
        if day not in model.DAYS:
            raise ValueError('Choose a weekday.')
        async with self._lock:
            before, rows = await self.snapshot(entity)
            self.check(before, revision)
            old = next((p for p in before['programmes'] if day in p['days']), None)
            p = model.programme({'id': old['id'] if old and len(old['days']) == 1 else 'day_' + day,
                                 'name': 'Heating schedule: ' + day, 'enabled': True, 'days': [day], 'slots': slots},
                                lambda v: model.heating_value(v, before['capabilities']))
            return await self.write(entity, before, rows, 'weekly', p, day=day)

    async def vacation(self, entity, revision, draft):
        model.keys(draft, ('enabled', 'value', 'slots'), ('enabled',))
        if ('value' in draft) == ('slots' in draft) or type(draft['enabled']) is not bool:
            raise ValueError('Vacation requires an enabled boolean and a timeline or constant value.')
        async with self._lock:
            before, rows = await self.snapshot(entity)
            self.check(before, revision)
            slots = draft.get('slots') if 'slots' in draft else [{
                'id': 'vacation_all_day', 'start': 0, 'end': 1440, 'value': draft['value']}]
            p = model.programme({'id': 'vacation', 'name': 'Heating schedule: vacation', 'enabled': True,
                                 'days': list(model.DAYS), 'slots': slots},
                                lambda v: model.heating_value(v, before['capabilities']))
            await self.write(entity, before, rows, 'vacation_schedule', p)
            try:
                await self.backend('call_service', domain='input_boolean',
                                   service='turn_on' if draft['enabled'] else 'turn_off',
                                   service_data={'entity_id': before['binding']['vacation']})
                await self.backend('call_service', domain='script', service=before['binding']['service'].split('.')[1], service_data={})
                for _ in range(30):
                    view = await self.load(entity)
                    if view['vacation']['enabled'] == draft['enabled']:
                        return view
                    await asyncio.sleep(0.1)
                raise PartialSave('Vacation toggle not confirmed.')
            except (ConnectionError, TimeoutError, ValueError) as error:
                raise PartialSave('Vacation was not fully confirmed. Reload before retrying; some changes may be saved.') from error
