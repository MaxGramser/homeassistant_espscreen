"""Schedule contracts: lossless validation, ownership, revisions and partial writes."""
import asyncio
from copy import deepcopy
import sys
from pathlib import Path
import unittest
import tempfile

from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screen_manager' / 'app'))
import heating_package
import schedule_model as model
import schedules
import test_scaling
from server import Manager, create_app

ENTITY = 'climate.test_heater'
BINDING = heating_package.binding(ENTITY)
CLIMATE = {'state': 'heat', 'attributes': {'hvac_modes': ['off', 'heat'], 'min_temp': 5,
                                          'max_temp': 30, 'target_temp_step': 0.5}}
CAPS = model.heating_capabilities(CLIMATE)


def programme():
    return {'id': 'weekdays', 'name': 'Weekdays', 'enabled': True, 'days': list(model.DAYS[:5]),
            'start_date': None, 'end_date': None, 'slots': [
                {'id': 'night', 'start': 0, 'end': 360, 'value': {'mode': 'off'}},
                {'id': 'day', 'start': 360, 'end': 1320, 'value': {'mode': 'heat', 'temperature': 20.5}},
                {'id': 'evening', 'start': 1320, 'end': 1440, 'value': {'mode': 'heat', 'temperature': 17}}]}


def projected(p):
    """Expected device presentation; HA, not metadata, owns interval identity."""
    p = deepcopy(p)
    p.update(id='ha_' + p['days'][0], name='Heating schedule: ' + p['days'][0])
    for slot in p['slots']:
        slot['id'] = f"ha_{slot['start']}_{slot['end']}"
        if not p['enabled']:
            slot['value'] = {'mode': 'off'}
    p['enabled'] = True
    return p


class ModelTests(unittest.TestCase):
    def test_schedule_tap_requires_shared_firmware_and_a_climate_entity(self):
        from core import min_firmware, validate_layout
        layout = validate_layout({'title': 'Heating', 'tiles': [
            {'entity': ENTITY, 'options': {'tap': 'schedule'}}]})
        self.assertEqual(min_firmware(layout), (0, 7, 0))
        self.assertEqual(min_firmware({'tiles': [*layout['tiles'], {'entity': 'lock.front_door'}]}), (0, 7, 0))
        with self.assertRaises(ValueError):
            validate_layout({'title': 'Heating', 'tiles': [
                {'entity': 'switch.heater', 'options': {'tap': 'schedule'}}]})

    def validate(self, p):
        return model.programme(p, lambda v: model.heating_value(v, CAPS))

    def test_off_is_not_zero_temperature(self):
        for bad in (0, float('nan'), float('inf'), 4, 30.5, 20.25, True, '20'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                model.heating_value({'mode': 'heat', 'temperature': bad}, CAPS)
        with self.assertRaises(ValueError):
            model.heating_value({'mode': 'off', 'temperature': 0}, CAPS)
        self.assertEqual(model.heating_value({'mode': 'off'}, CAPS), {'mode': 'off'})

    def test_intervals_reject_gaps_overlap_and_unsnapped_boundaries(self):
        for start, end in [(361, 1320), (355, 1320), (360, 360), (360, 1445), (360, 1321)]:
            p = programme()
            p['slots'][1].update(start=start, end=end)
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                self.validate(p)

    def test_unknown_value_and_fields_do_not_disappear(self):
        for change in ({'value': {'mode': 'cool', 'temperature': 20}}, {'script': 'example'}, {'id': 'night'}):
            p = programme()
            p['slots'][1].update(change)
            with self.assertRaises(ValueError):
                self.validate(p)

    def test_generic_split_and_merge_preserve_non_heating_values(self):
        slots = [{'id': 'a', 'start': 0, 'end': 1440, 'value': {'brightness': 70}}]
        divided = model.split(slots, 0, 720, 'b')
        self.assertEqual([s['value'] for s in divided], [{'brightness': 70}] * 2)
        divided[1]['value']['brightness'] = 25
        self.assertEqual(model.merge(divided, 1), slots)
        self.assertEqual(model.merge(divided, 0)[0]['value'], {'brightness': 25})
        self.assertEqual(slots[0]['value'], {'brightness': 70})
        for minute in (0, 1, 719, 1440):
            with self.assertRaises(ValueError):
                model.split(slots, 0, minute, 'b')

    def test_linked_days_and_disabled_programmes(self):
        a, b = programme(), programme()
        b['id'] = 'weekend'
        b['days'] = ['sat', 'sun']
        model.no_overlaps([a, b])
        b['days'].append('fri')
        with self.assertRaises(ValueError):
            model.no_overlaps([a, b])
        b['enabled'] = False
        model.no_overlaps([a, b])




def backend_row(p=None):
    p = p or programme()
    # Existing metadata-rich blocks remain readable without migration or writes.
    blocks = [{'from': schedules.clock(s['start']), 'to': schedules.clock(s['end']), 'data': {
        'esp_screen': BINDING['key'], 'programme': p['id'], 'name': p['name'],
        'enabled': p['enabled'], 'slot': s['id'], **s['value']}} for s in p['slots']]
    return {**schedules.blank(BINDING, 'weekly'),
            **{schedules.WEEKDAYS[d]: deepcopy(blocks) for d in p['days']}}


class FakeBackend:
    def __init__(self):
        self.rows, self.writes = [], []
        self.fail, self.drop_write = None, False
        self.states = {ENTITY: deepcopy(CLIMATE), BINDING['service']: {
            'state': 'off', 'attributes': {'esp_screen_controller': heating_package.CONTROLLER_VERSION}},
            BINDING['reconcile']: {'state': 'on'}, BINDING['vacation']: {'state': 'off'}}
        self.registry = [{'entity_id': BINDING[k], 'hidden_by': None} for k in ('service', 'reconcile', 'vacation')]

    async def __call__(self, kind, **data):
        if kind == 'schedule/list':
            return deepcopy(self.rows)
        if kind == 'config/entity_registry/list':
            return deepcopy(self.registry)
        if self.fail == kind:
            raise ConnectionError('Test failure')
        self.writes.append((kind, deepcopy(data)))
        if kind == 'schedule/create':
            row = {'id': data['name'], **deepcopy(data)}
            self.rows.append(row)
            self.registry.append({'entity_id': 'schedule.' + row['id'], 'hidden_by': None})
            return deepcopy(row)
        if kind == 'schedule/update':
            if not self.drop_write:
                i = next(i for i, r in enumerate(self.rows) if r['id'] == data['schedule_id'])
                self.rows[i] = {'id': data['schedule_id'], **{k: deepcopy(v) for k, v in data.items() if k != 'schedule_id'}}
            return {}
        if kind == 'config/entity_registry/update':
            next(r for r in self.registry if r['entity_id'] == data['entity_id']).update(data)
        if kind == 'call_service' and data['domain'] == 'input_boolean':
            self.states[data['service_data']['entity_id']]['state'] = 'on' if data['service'] == 'turn_on' else 'off'
        return {}


class CodecTests(unittest.TestCase):
    def test_legacy_days_disabled_blocks_and_midnight_project_correctly(self):
        for enabled in (True, False):
            p = programme(); p['enabled'] = enabled
            row = backend_row(p)
            self.assertEqual(row['monday'][-1]['to'], '24:00:00')
            self.assertEqual(schedules.decode(row, BINDING, CAPS), [projected(p)])
            self.assertEqual(row['monday'][1]['data']['slot'], 'day')

    def test_unsupported_data_is_rejected_not_discarded(self):
        for field, value in [('temperature', 100), ('esp_screen', 'another-owner'), ('mode', 'cool'), ('unknown', True)]:
            row = backend_row()
            row['monday'][1]['data'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                schedules.decode(row, BINDING, CAPS)
        for end in ('00:00:00', '23:59:59', '24:00:01'):
            row = backend_row(); row['monday'][-1]['to'] = end
            with self.subTest(end=end), self.assertRaises(ValueError):
                schedules.decode(row, BINDING, CAPS)

    def test_unknown_helper_fields_are_readonly_and_gaps_are_off(self):
        row = backend_row(); row['new_field'] = 1
        with self.assertRaises(ValueError):
            schedules.decode(row, BINDING, CAPS)
        row = backend_row(); row['monday'].pop(1)
        decoded = schedules.decode(row, BINDING, CAPS)
        monday = next(p for p in decoded if 'mon' in p['days'])
        self.assertEqual(monday['slots'][1]['value'], {'mode': 'off'})
        self.assertEqual(monday['days'], ['mon'])

    def test_native_blocks_need_no_internal_metadata(self):
        row = schedules.blank(BINDING, 'weekly')
        row['monday'] = [{'from': '06:00:00', 'to': '22:00:00', 'data': {'temperature': 20.5}}]
        day = schedules.decode(row, BINDING, CAPS)[0]
        self.assertEqual([(s['start'], s['end'], s['value']) for s in day['slots']], [
            (0, 360, {'mode': 'off'}), (360, 1320, {'mode': 'heat', 'temperature': 20.5}),
            (1320, 1440, {'mode': 'off'})])
        for data in ({}, {'temperature': 0}, {'mode': 'off', 'temperature': 20}, {'enabled': False, 'temperature': 20}):
            row['monday'][0]['data'] = data
            self.assertTrue(all(s['value'] == {'mode':'off'} for s in schedules.decode(row, BINDING, CAPS)[0]['slots']))
        del row['monday'][0]['data']
        self.assertTrue(all(s['value'] == {'mode':'off'} for s in schedules.decode(row, BINDING, CAPS)[0]['slots']))

    def test_linked_day_edit_and_copied_metadata_do_not_link_native_days(self):
        row = backend_row()
        row['tuesday'][1]['data']['temperature'] = 23
        # HA users can change, omit or copy these irrelevant editor IDs.
        for block in row['tuesday']:
            block['data'].update(programme='different', slot='duplicate', name='Different label')
        before = deepcopy(row)
        days = schedules.decode(row, BINDING, CAPS)
        self.assertEqual(next(p for p in days if 'tue' in p['days'])['days'], ['tue'])
        self.assertEqual(next(p for p in days if 'mon' in p['days'])['days'], ['mon','wed','thu','fri'])
        self.assertEqual(row, before, 'Reading never normalises HA storage')

    def test_ordering_and_unsupported_boundaries_are_never_silently_changed(self):
        row = backend_row(); row['monday'].reverse()
        self.assertEqual(schedules.decode(row, BINDING, CAPS), [projected(programme())])
        for data in ({'temperature': True}, {'temperature':'20'}, {'enabled':0}, {'mode':'heat'}, {'temperature':float('nan')}):
            row = backend_row(); row['monday'][1]['data'] = data
            with self.subTest(data=data), self.assertRaises(ValueError):
                schedules.decode(row, BINDING, CAPS)
        row = backend_row(); row['monday'][0]['to'] = '06:01:00'; row['monday'][1]['from'] = '06:01:00'
        with self.assertRaisesRegex(ValueError, 'five-minute'):
            schedules.decode(row, BINDING, CAPS)
        row['monday'][1]['from'] = '06:00:00'
        with self.assertRaisesRegex(ValueError, 'overlap'):
            schedules.decode(row, BINDING, CAPS)


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.adapter = schedules.Adapter(self.backend, lambda: self.backend.states, lambda: {'temperature': '°C'})

    async def save(self, p):
        before = await self.adapter.load(ENTITY)
        return await self.adapter.save(ENTITY, before['revision'], p)

    async def test_load_does_not_create_any_helpers(self):
        await self.adapter.load(ENTITY)
        self.assertEqual(self.backend.writes, [])

    async def test_create_edit_readback_and_hide_without_calendar_writes(self):
        p = programme()
        after = await self.save(p)
        self.assertEqual(after['programmes'], [projected(p)])
        self.assertEqual(len(self.backend.rows), 2)
        self.assertTrue(all(r['hidden_by'] == 'user' for r in self.backend.registry))
        p = deepcopy(after['programmes'][0]); p['slots'][1]['value']['temperature'] = 21
        after = await self.save(p)
        self.assertEqual(after['programmes'], [p])
        self.assertEqual(len(self.backend.rows), 2)
        self.assertFalse(any('calendar' in kind for kind, _ in self.backend.writes))

    async def test_user_visibility_choice_survives_later_saves(self):
        p = programme()
        after = await self.save(p)
        self.backend.registry[-1]['hidden_by'] = None
        await self.save(after['programmes'][0])
        self.assertIsNone(self.backend.registry[-1]['hidden_by'])

    async def test_disabled_programme_retains_values_but_marks_every_block_disabled(self):
        p = programme(); p['enabled'] = False
        after = await self.save(p)
        self.assertEqual(after['programmes'], [projected(p)])
        self.assertTrue(all(not r['data']['enabled'] for r in self.backend.rows[0]['monday']))
        self.assertEqual(self.backend.rows[0]['monday'][1]['data']['temperature'], 20.5)

    async def test_outdated_revision_and_external_edit(self):
        self.backend.rows = [backend_row()]
        before = await self.adapter.load(ENTITY)
        self.backend.rows[0]['monday'][1]['data']['temperature'] = 22
        with self.assertRaises(schedules.Conflict):
            await self.adapter.save(ENTITY, before['revision'], programme())
        self.assertEqual(self.backend.writes, [])

    async def test_timer_ticks_do_not_conflict_but_override_and_config_changes_do(self):
        self.backend.rows = [backend_row()]
        before = await self.adapter.load(ENTITY)
        self.backend.states[BINDING['weekly']] = {'state': 'on', 'attributes': {'next_event': 'tomorrow', 'temperature': 20}}
        self.assertEqual(before['revision'], (await self.adapter.load(ENTITY))['revision'])
        self.backend.states[BINDING['vacation']]['state'] = 'on'
        self.assertNotEqual(before['revision'], (await self.adapter.load(ENTITY))['revision'])

    async def test_foreign_helpers_and_visibility_are_untouched(self):
        foreign = {**backend_row(), 'id': 'someone_else'}
        self.backend.rows = [deepcopy(foreign)]
        self.backend.registry.append({'entity_id': 'schedule.someone_else', 'hidden_by': None})
        await self.save(programme())
        self.assertEqual(self.backend.rows[0], foreign)
        self.assertIsNone(self.backend.registry[3]['hidden_by'])

    async def test_unsupported_owned_data_blocks_saves(self):
        self.backend.rows = [backend_row()]
        self.backend.rows[0]['monday'][0]['data']['esp_screen'] = 'someone_else'
        before = await self.adapter.load(ENTITY)
        self.assertEqual(len(before['readonly']), 1)
        with self.assertRaises(ValueError):
            await self.adapter.save(ENTITY, before['revision'], programme())
        self.assertEqual(self.backend.writes, [])

    async def test_missing_or_old_controller_blocks_writes(self):
        for attributes in ({}, {'esp_screen_controller':'native_schedule_v1'}):
            self.backend.states[BINDING['service']]['attributes'] = attributes
            with self.assertRaises(schedules.Unavailable):
                await self.save(programme())
        self.assertEqual(self.backend.writes, [])
        self.adapter.units = lambda: {'temperature': '°F'}
        with self.assertRaises(ValueError):
            await self.adapter.load(ENTITY)

    async def test_partial_write_and_unconfirmed_write_are_not_success(self):
        self.backend.fail = 'schedule/update'
        with self.assertRaises(schedules.PartialSave):
            await self.save(programme())
        self.backend.fail = None
        self.backend.drop_write = True
        with self.assertRaises(schedules.PartialSave):
            await self.save(programme())

    async def test_two_clients_same_revision_only_one_wins(self):
        before = await self.adapter.load(ENTITY)
        results = await asyncio.gather(*(self.adapter.save(ENTITY, before['revision'], programme()) for _ in range(2)), return_exceptions=True)
        self.assertEqual(sum(isinstance(r, schedules.Conflict) for r in results), 1)

    async def test_edit_one_day_preserves_other_days_in_one_update(self):
        self.backend.rows = [backend_row()]
        before = await self.adapter.load(ENTITY)
        other_days = deepcopy(self.backend.rows[0])
        slots = deepcopy(programme()['slots']); slots[1]['value']['temperature'] = 24
        after = await self.adapter.save_day(ENTITY, before['revision'], 'mon', slots)
        self.assertEqual(next(p for p in after['programmes'] if p['days'] == ['mon'])['slots'], projected({**programme(), 'slots':slots})['slots'])
        remaining = next(p for p in after['programmes'] if 'tue' in p['days'])
        self.assertEqual(remaining['days'], ['tue', 'wed', 'thu', 'fri'])
        for day in list(schedules.WEEKDAYS.values())[1:]:
            self.assertEqual(self.backend.rows[0][day], other_days[day])
        self.assertEqual(sum(kind == 'schedule/update' and data['schedule_id'] == BINDING['weekly'].split('.')[1] for kind, data in self.backend.writes), 1)

    async def test_invalid_days_slots_dates_and_overlaps_never_write(self):
        self.backend.rows = [backend_row()]
        before = await self.adapter.load(ENTITY)
        for day, slots in [('vacation', programme()['slots']), ('mon', [])]:
            with self.assertRaises(ValueError):
                await self.adapter.save_day(ENTITY, before['revision'], day, slots)
        p = programme(); p['start_date'] = '2026-09-26'
        with self.assertRaises(ValueError):
            await self.save(p)
        p = programme(); p['id'] = 'other'
        with self.assertRaises(ValueError):
            await self.save(p)
        self.assertEqual(self.backend.writes, [])

    async def test_native_gap_roundtrip_preserves_gaps_other_days_and_unchanged_metadata(self):
        row = backend_row()
        row['monday'] = [{'from':'06:00:00','to':'12:00:00','data':{'temperature':20}},
                         {'from':'14:00:00','to':'22:00:00','data':{'temperature':18,'name':'Keep this'}}]
        self.backend.rows = [row]
        original = deepcopy(row)
        before = await self.adapter.load(ENTITY)
        slots = deepcopy(next(p for p in before['programmes'] if 'mon' in p['days'])['slots'])
        slots[1]['value']['temperature'] = 21
        after = await self.adapter.save_day(ENTITY, before['revision'], 'mon', slots)
        expected = deepcopy(original); expected['monday'][0]['data'] = {'temperature':21}
        self.assertEqual(self.backend.rows[0], expected)
        self.assertFalse(after['readonly'])
        self.assertEqual(next(p for p in after['programmes'] if 'mon' in p['days'])['slots'], slots)

    async def test_split_off_period_survives_save_even_when_all_day_is_off(self):
        before = await self.adapter.load(ENTITY)
        slots = [{'id':'one','start':0,'end':720,'value':{'mode':'off'}},
                 {'id':'two','start':720,'end':1440,'value':{'mode':'off'}}]
        after = await self.adapter.save_day(ENTITY, before['revision'], 'mon', slots)
        self.assertEqual(len(after['programmes'][0]['slots']), 2)
        self.assertEqual([s['data'] for s in self.backend.rows[0]['monday']], [{'temperature':0}]*2)

    async def test_ha_edit_during_preparation_is_a_conflict_not_partial_success(self):
        self.backend.rows = [backend_row(), schedules.blank(BINDING,'vacation_schedule')]
        before = await self.adapter.load(ENTITY)
        reads = 0
        async def concurrent_backend(kind, **data):
            nonlocal reads
            if kind == 'schedule/list':
                reads += 1
                if reads == 2:
                    self.backend.rows[0]['tuesday'][1]['data']['temperature'] = 23
            return await self.backend(kind, **data)
        self.adapter.backend = concurrent_backend
        with self.assertRaises(schedules.Conflict):
            await self.adapter.save_day(ENTITY,before['revision'],'mon',programme()['slots'])
        self.assertEqual(self.backend.rows[0]['tuesday'][1]['data']['temperature'],23)
        self.assertEqual(self.backend.writes, [])

    async def test_readonly_reason_reaches_panel_and_external_data_is_not_rewritten(self):
        row = backend_row(); row['monday'][0]['data']['custom_action'] = 'keep'
        self.backend.rows = [row]
        original = deepcopy(row)
        view = await self.adapter.load(ENTITY)
        self.assertIn(view['readonly'][0]['reason'], view['warnings'][0])
        with self.assertRaises(ValueError):
            await self.adapter.save_day(ENTITY,view['revision'],'tue',programme()['slots'])
        self.assertEqual(self.backend.rows[0], original)
        self.assertEqual(self.backend.writes, [])

    async def test_vacation_daily_timeline_and_exit_preserve_weekdays(self):
        self.backend.rows = [backend_row()]
        weekday = deepcopy(self.backend.rows[0])
        before = await self.adapter.load(ENTITY)
        slots = deepcopy(programme()['slots']); slots[1]['value']['temperature'] = 16
        after = await self.adapter.vacation(ENTITY, before['revision'], {'enabled': True, 'slots': slots})
        self.assertTrue(after['vacation']['enabled'])
        self.assertEqual(after['vacation_programme']['slots'], projected({**programme(), 'slots':slots})['slots'])
        self.assertEqual(after['vacation_programme']['days'], list(model.DAYS))
        self.assertEqual(self.backend.rows[0], weekday)
        holiday = self.backend.rows[1]
        self.assertTrue(all(holiday[d] == holiday['monday'] for d in schedules.WEEKDAYS.values()))
        after = await self.adapter.vacation(ENTITY, after['revision'], {'enabled': False, 'slots': slots})
        self.assertFalse(after['vacation']['enabled'])
        self.assertEqual(after['vacation_programme']['slots'], projected({**programme(), 'slots':slots})['slots'])
        self.assertEqual(self.backend.rows[0], weekday)

    async def test_constant_vacation_maps_to_one_full_day_slot(self):
        before = await self.adapter.load(ENTITY)
        value = {'mode': 'heat', 'temperature': 16.5}
        after = await self.adapter.vacation(ENTITY, before['revision'], {'enabled': True, 'value': value})
        self.assertEqual(after['vacation'], {'enabled': True, 'value': value})
        self.assertEqual(len(after['vacation_programme']['slots']), 1)

    async def test_vacation_flag_failure_is_partial_and_keeps_weekdays(self):
        self.backend.rows = [backend_row()]
        self.backend.fail = 'call_service'
        before = await self.adapter.load(ENTITY)
        with self.assertRaises(schedules.PartialSave):
            await self.adapter.vacation(ENTITY, before['revision'], {'enabled': True, 'slots': programme()['slots']})
        self.assertEqual(self.backend.rows[0], backend_row())


class PackageTests(unittest.TestCase):
    def test_controller_and_adapter_agree_on_native_and_legacy_values(self):
        from jinja2 import Environment
        template = heating_package.package(ENTITY,CAPS)['script'][BINDING['service'].split('.')[1]]['sequence'][2]['variables']['selected']
        cases = [({},0), ({'temperature':20.5},20.5), ({'temperature':0},0),
                 ({'mode':'off','temperature':20},0), ({'enabled':False,'temperature':20},0),
                 ({'esp_screen':BINDING['key'],'enabled':True,'mode':'heat','temperature':17},17),
                 ({'mode':'heat'},-1), ({'temperature':True},-1), ({'temperature':'20'},-1),
                 ({'mode':'cool','temperature':20},-1), ({'enabled':0,'temperature':20},-1),
                 ({'esp_screen':'other','temperature':20},-1)]
        for data, target in cases:
            with self.subTest(data=data):
                rendered = Environment().from_string(template).render(source='test',
                    is_state=lambda _,value:value=='on', state_attr=lambda _,key:data.get(key))
                self.assertEqual(float(rendered),target)
                if target == -1:
                    with self.assertRaises(ValueError):
                        schedules.block_value(data,BINDING,CAPS)
                else:
                    value = schedules.block_value(data,BINDING,CAPS)
                    self.assertEqual(value.get('temperature',0),target)

    def test_controller_is_native_and_reconciles_attributes_and_restart(self):
        p = heating_package.package(ENTITY, CAPS)
        self.assertNotIn('input_number', p)
        self.assertNotIn('scheduler.', str(p))
        self.assertNotIn('time_pattern', str(p))
        self.assertNotIn('initial', p['input_boolean'][BINDING['vacation'].split('.')[1]])
        script = p['script'][BINDING['service'].split('.')[1]]
        self.assertEqual(script['mode'], 'queued')
        trigger = p['automation'][0]['triggers'][0]
        self.assertIn(BINDING['weekly'], trigger['entity_id'])
        self.assertNotIn('to', trigger)
        self.assertNotIn('from', trigger)
        self.assertEqual(p['automation'][0]['triggers'][1]['event'], 'start')
class EndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_csrf_schema_conflict_and_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FakeBackend()
            ha = test_scaling.fake_ha()
            ha.states.update(backend.states)
            ha.units = {'temperature': '°C'}
            ha.schedule_api = backend
            manager = Manager(ha, Path(tmp) / 'screens.json')
            async with TestClient(TestServer(create_app(manager, True))) as client:
                csrf = (await (await client.get('/api/inventory?light=1')).json())['csrf']
                view = await (await client.get('/api/schedules', params={'entity': ENTITY})).json()
                request = {'v': 1, 'op': 'save', 'entity': ENTITY, 'revision': view['revision'], 'programme': programme()}
                self.assertEqual((await client.post('/api/schedules', json=request)).status, 403)
                headers = {'X-Screen-CSRF': csrf}
                self.assertEqual((await client.post('/api/schedules', json={**request, 'v': True}, headers=headers)).status, 400)
                self.assertEqual(backend.writes, [])
                self.assertEqual((await client.post('/api/schedules', json=request, headers=headers)).status, 200)
                conflict = await client.post('/api/schedules', json=request, headers=headers)
                self.assertEqual(conflict.status, 409)
                self.assertEqual((await conflict.json())['code'], 'schedule_conflict')
                package = await client.get('/api/schedules/package', params={'entity': ENTITY})
                self.assertEqual(package.status, 200)
                self.assertNotIn('scheduler.run_action', await package.text())


if __name__ == '__main__':
    unittest.main()
