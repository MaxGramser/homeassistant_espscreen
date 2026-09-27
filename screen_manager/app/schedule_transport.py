"""Bounded schedule exchange for the device's ESPHome event channel.

Rendering stays in firmware. Each programme travels separately within the
existing 4096-byte inbox limit; begin/end and a request ID make assembly atomic.
"""
import json
import secrets

import schedule_model as model
import schedules

EVENT = 'esphome.screen_schedule'


def packets(view, request):
    programmes = view['programmes']
    if len(programmes) > model.MAX_PROGRAMMES:
        raise ValueError('Too many programmes for this editor.')
    base = {'v': 1, 'op': 'schedule', 'rid': request['rid'], 'entity': request['entity']}
    warning = '\n'.join(view['warnings'])
    vacation = {**view['vacation'], 'slots': view['vacation_programme']['slots'] if view.get('vacation_programme') else [
        {'id': 'vacation_all_day', 'start': 0, 'end': 1440, 'value': view['vacation']['value'] or {'mode': 'off'}}]}
    begin = {**base, 'stage': 'begin', 'revision': view['revision'],
             'nonce': secrets.token_hex(8),
             'capabilities': view['capabilities'], 'count': len(programmes),
             'ready': view['controller_ready'] and not view['readonly'],
             'warning': warning[:600], 'vacation': vacation}
    if not view['controller_ready']:
        begin['warning'] = 'Install or update the heating controller package in Home Assistant before saving.'
    result = [begin, *[{**base, 'stage': 'programme', 'index': i, 'programme': p}
                       for i, p in enumerate(programmes)], {**base, 'stage': 'end'}]
    for packet in result:
        if len(json.dumps(packet, ensure_ascii=False, separators=(',', ':')).encode()) > 4096:
            raise ValueError('Schedule exceeds the firmware message limit.')
    return result


async def exchange(adapter, payload, entities):
    if not isinstance(payload, str) or len(payload.encode()) > 4096:
        raise ValueError('Invalid schedule payload.')
    request = json.loads(payload)
    model.keys(request, ('v', 'rid', 'entity', 'op', 'revision', 'programme', 'vacation', 'day', 'slots'),
               ('v', 'rid', 'entity', 'op'))
    if type(request['v']) is not int or request['v'] != 1 or type(request['rid']) is not int or not 0 < request['rid'] <= 0xFFFFFFFF:
        raise ValueError('Unsupported schedule protocol.')
    entity = request['entity']
    if not isinstance(entity, str) or entity not in entities:
        raise ValueError('Schedule must belong to a heating tile on this screen.')
    try:
        op = request['op']
        if op == 'load' and not set(request) & {'revision', 'programme', 'vacation', 'day', 'slots'}:
            view = await adapter.load(entity)
        elif op == 'day' and not set(request) & {'programme', 'vacation'}:
            view = await adapter.save_day(entity, request.get('revision'), request.get('day'), request.get('slots'))
        elif op == 'save' and not set(request) & {'vacation', 'day', 'slots'}:
            view = await adapter.save(entity, request.get('revision'), request.get('programme'))
        elif op == 'vacation' and not set(request) & {'programme', 'day', 'slots'}:
            view = await adapter.vacation(entity, request.get('revision'), request.get('vacation'))
        else:
            raise ValueError('Unsupported schedule operation.')
        return packets(view, request)
    except (ValueError, ConnectionError, TimeoutError) as error:
        code = 'conflict' if isinstance(error, schedules.Conflict) else 'unconfirmed' if isinstance(error, schedules.PartialSave) else 'unavailable' if isinstance(error, (ConnectionError, TimeoutError)) else 'invalid'
        return [{'v': 1, 'op': 'schedule', 'rid': request['rid'], 'entity': entity,
                 'stage': 'error', 'code': code, 'message': str(error)[:600]}]


def bound_entities(layout):
    return {t['entity'] for t in layout['tiles'] if t['entity'].startswith('climate.') and
            t.get('options', {}).get('tap') == 'schedule'}
