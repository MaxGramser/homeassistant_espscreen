"""What the editor's first layout reads of a home (docs/AUTO_LAYOUT.md): the facts of Home Assistant's registries that the
inventory leaves out, for every entity a tile can show. Its area and device by id, its category (config, diagnostic),
whether Home Assistant hides it, its device class, state class and unit, whether it is a group of others, and whether it
belongs to one of the screens; the areas (with the temperature and humidity sensors Home Assistant shows for each) and floors in Home Assistant's own order, and the devices by id.

Pure: the registries and states in, a JSON-ready answer out. The layout itself is worked out in the editor
(web/src/model/auto-layout.ts); nothing here decides what goes on a screen. tests/test_home_facts.py.
"""
from core import entity_id


def _floor_order(floors):
    """Floors as Home Assistant lists them, which is the order its own dashboards and area pickers follow."""
    return [{'id': floor.get('floor_id'), 'name': floor.get('name') or '', 'level': floor.get('level'),
             **({'icon': floor['icon']} if isinstance(floor.get('icon'), str) else {})}
            for floor in floors or [] if isinstance(floor, dict) and floor.get('floor_id')]


def facts(registry, states, devices, areas, floors, screen_devices=()):
    """The facts for every entity a tile can show that Home Assistant has not disabled (core.discover's set).

    `screen_devices`: the device ids of the paired screens; their own entities say `screen` so a layout leaves them out.
    """
    device_map = {d['id']: d for d in devices or [] if isinstance(d, dict) and d.get('id')}
    screen_devices = set(screen_devices)
    registered, entities, used_devices = set(), [], set()

    def one(eid, item, state):
        attributes = (state or {}).get('attributes') or {}
        device_id = item.get('device_id') or ''
        device = device_map.get(device_id, {})
        area = item.get('area_id') or device.get('area_id') or ''
        members = attributes.get('entity_id')
        fact = {'id': eid, 'area': area, 'device': device_id}
        if device_id:
            used_devices.add(device_id)
        if item.get('entity_category') in ('config', 'diagnostic'):
            fact['category'] = item['entity_category']
        if item.get('hidden_by') or attributes.get('hidden'):
            fact['hidden'] = True
        if isinstance(item.get('platform'), str):
            fact['platform'] = item['platform']
        device_class = attributes.get('device_class') or item.get('device_class') or item.get('original_device_class')
        if isinstance(device_class, str) and device_class:
            fact['class'] = device_class
        for key, name in (('state_class', 'stateClass'), ('unit_of_measurement', 'unit')):
            if isinstance(attributes.get(key), str) and attributes[key]:
                fact[name] = attributes[key]
        # A group of lights, covers or players (a light group, a Hue room, a speaker group): its members by id.
        if isinstance(members, list) and members and all(isinstance(m, str) for m in members):
            fact['members'] = members[:32]
        if device_id and device_id in screen_devices:
            fact['screen'] = True
        if isinstance(attributes.get('supported_features'), int):
            fact['features'] = attributes['supported_features']
        return fact

    for item in registry or []:
        eid = item.get('entity_id') if isinstance(item, dict) else None
        if not isinstance(eid, str):
            continue
        registered.add(eid)
        if not entity_id(eid) or item.get('disabled_by'):
            continue
        entities.append(one(eid, item, states.get(eid)))
    # YAML entities without a registry entry: no area, no device, only what their state says.
    for eid, state in (states or {}).items():
        if eid not in registered and entity_id(eid):
            entities.append(one(eid, {}, state))
    area_list = [{'id': area.get('area_id'), 'name': area.get('name') or '',
                  **({'floor': area['floor_id']} if area.get('floor_id') else {}),
                  **({'icon': area['icon']} if isinstance(area.get('icon'), str) else {}),
                  # The area's own temperature and humidity sensors (Home Assistant 2025.x), which its area card shows.
                  **({'temperature': area['temperature_entity_id']} if isinstance(area.get('temperature_entity_id'), str) else {}),
                  **({'humidity': area['humidity_entity_id']} if isinstance(area.get('humidity_entity_id'), str) else {})}
                 for area in areas or [] if isinstance(area, dict) and area.get('area_id')]
    device_list = {device_id: {'name': device.get('name_by_user') or device.get('name') or '',
                               **({'area': device['area_id']} if device.get('area_id') else {}),
                               **({'model': device['model']} if isinstance(device.get('model'), str) else {}),
                               **({'maker': device['manufacturer']} if isinstance(device.get('manufacturer'), str) else {}),
                               **({'service': True} if device.get('entry_type') == 'service' else {})}
                   for device_id, device in device_map.items() if device_id in used_devices}
    return {'entities': entities, 'areas': area_list, 'floors': _floor_order(floors), 'devices': device_list}
