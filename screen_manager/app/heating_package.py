"""Standard HA controller for native Schedule helpers; no manager-side timer."""
import hashlib
import re

CONTROLLER_VERSION = 'native_schedule_v2'


def binding(entity):
    if not isinstance(entity, str) or not re.fullmatch(r'climate\.[a-z0-9_]+', entity):
        raise ValueError('A climate entity is required.')
    key = 'esp_screen_heat_' + hashlib.sha256(entity.encode()).hexdigest()[:12]
    return {'entity': entity, 'key': key, 'weekly': 'schedule.' + key + '_weekly',
            'vacation_schedule': 'schedule.' + key + '_vacation',
            'service': 'script.' + key + '_native_apply',
            'reconcile': 'automation.' + key + '_native_reconcile',
            'vacation': 'input_boolean.' + key + '_vacation'}


def package(entity, capabilities):
    b = binding(entity)
    source = "{{ '" + b['vacation_schedule'] + "' if is_state('" + b['vacation'] + "', 'on') else '" + b['weekly'] + "' }}"
    selection = """
{% set owner = state_attr(source, 'esp_screen') %}
{% set enabled = state_attr(source, 'enabled') %}
{% set mode = state_attr(source, 'mode') %}
{% set temperature = state_attr(source, 'temperature') %}
{% if is_state(source, 'off') %}0
{% elif not is_state(source, 'on') or (owner is not none and owner != OWNER)
     or (enabled is not none and enabled is not boolean) or mode not in [none, 'off', 'heat'] %}-1
{% elif enabled == false or mode == 'off' %}0
{% elif temperature is number and temperature is not boolean %}{{ temperature }}
{% elif temperature is none and mode is none %}0
{% else %}-1{% endif %}
""".strip().replace('OWNER', repr(b['key']))
    valid = ("{{ selected == 0 or (selected >= " + str(capabilities['min']) +
             " and selected <= " + str(capabilities['max']) +
             " and (((selected - " + str(capabilities['min']) + ") / " + str(capabilities['step']) +
             ") - (((selected - " + str(capabilities['min']) + ") / " + str(capabilities['step']) +
             ") | round)) | abs < 0.000001) }}")
    script = {
        'alias': 'ESP Screen heating: ' + entity, 'mode': 'queued', 'max': 50,
        'description': 'Apply the current native Schedule block. Vacation takes precedence.',
        'sequence': [
            {'condition': 'template', 'value_template': "{{ has_value('" + entity + "') and has_value('" + b['vacation'] + "') }}"},
            {'variables': {'source': source}},
            {'variables': {'selected': selection}},
            {'condition': 'template', 'value_template': valid},
            {'choose': [{'conditions': '{{ selected == 0 }}', 'sequence': [
                {'action': 'climate.set_hvac_mode', 'target': {'entity_id': entity}, 'data': {'hvac_mode': 'off'}}]}],
             'default': [{'action': 'climate.set_temperature', 'target': {'entity_id': entity},
                          'data': {'temperature': '{{ selected }}', 'hvac_mode': 'heat'}}]},
        ]}
    return {
        'homeassistant': {'customize': {b['service']: {'esp_screen_controller': CONTROLLER_VERSION}}},
        'input_boolean': {b['vacation'].split('.')[1]: {
            'name': 'Heating vacation: ' + entity, 'icon': 'mdi:bag-suitcase'}},
        'script': {b['service'].split('.')[1]: script},
        'automation': [{
            'id': b['reconcile'].split('.')[1], 'alias': b['reconcile'].split('.')[1],
            'mode': 'queued', 'max': 50,
            # No to/from on schedule triggers: adjacent blocks stay "on" but
            # their attributes change, including blocks with the same setpoint.
            'triggers': [
                {'trigger': 'state', 'entity_id': [b['weekly'], b['vacation_schedule'], b['vacation']]},
                {'trigger': 'homeassistant', 'event': 'start'},
                {'trigger': 'state', 'entity_id': entity, 'from': 'unavailable'},
                {'trigger': 'state', 'entity_id': entity, 'from': 'unknown'}],
            'actions': [{'action': b['service']}],
        }],
    }
