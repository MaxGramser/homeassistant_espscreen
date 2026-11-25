"""Home Assistant's states as its own frontend follows them: the websocket command `subscribe_entities`.

What it is: the translation of that subscription's compressed messages into the states this app keeps
(`HomeAssistant.states`, {entity_id: {entity_id, state, attributes, last_changed, last_updated, context}}), the same
shape `get_states` and a `state_changed` event give.

Why (GitHub #315, #392, #399, #428): `get_states` hands over every state in one message, and `state_changed` hands over
the whole old and new state of every change. A home with a few very large entities (a sports sensor of 6 MB) passed the
message limit or the wait for the first list, and every change of such an entity sent its megabytes twice. This
subscription sends the states once with short keys and then only what changed of each, down to the attribute.

It follows home-assistant-js-websocket's `entities.ts` (processEvent), the frontend's own reader of these messages:
  {"a": {id: {"s": state, "a": attributes, "c": context id or object, "lc": epoch, "lu": epoch}}}  added or whole
  {"c": {id: {"+": {"s", "a", "c", "lc", "lu"} of what changed, "-": {"a": [attribute names gone]}}}}  changed
  {"r": [id, ...]}  removed
What it does not know: anything about screens or tiles. tests/test_ha_entities.py proves it.
"""
from datetime import datetime, timezone


def moment(epoch):
    """An epoch of the subscription as the ISO text `get_states` gives (`2026-11-24T10:00:00.123456+00:00`)."""
    return datetime.fromtimestamp(float(epoch), timezone.utc).isoformat()


def context_of(value, before=None):
    """The context as a state carries it: the subscription sends its id alone when nothing else is set."""
    if isinstance(value, str):
        return {**(before or {'parent_id': None, 'user_id': None}), 'id': value}
    if isinstance(value, dict):
        return {**(before or {}), **value}
    return before


def whole(entity_id, compressed):
    """One state from its compressed form in "a"."""
    changed = moment(compressed['lc']) if compressed.get('lc') is not None else None
    updated = moment(compressed['lu']) if compressed.get('lu') is not None else changed
    return {'entity_id': entity_id, 'state': compressed.get('s'), 'attributes': compressed.get('a') or {},
            'last_changed': changed or updated, 'last_updated': updated or changed,
            'context': context_of(compressed.get('c'))}


def apply(states, update):
    """Puts one message of the subscription into `states` (changed in place) and returns the entity ids it touched.
    A change for an entity this app has no state of is left out, as the frontend does."""
    touched = set()
    for entity_id, compressed in (update.get('a') or {}).items():
        if isinstance(compressed, dict):
            states[entity_id] = whole(entity_id, compressed)
            touched.add(entity_id)
    for entity_id in update.get('r') or []:
        if states.pop(entity_id, None) is not None:
            touched.add(entity_id)
    for entity_id, diff in (update.get('c') or {}).items():
        state = states.get(entity_id)
        if state is None or not isinstance(diff, dict):
            continue
        state = dict(state)
        plus, minus = diff.get('+') or {}, diff.get('-') or {}
        if plus.get('a') or minus.get('a'):
            attributes = dict(state.get('attributes') or {})
            attributes.update(plus.get('a') or {})
            for name in minus.get('a') or []:
                attributes.pop(name, None)
            state['attributes'] = attributes
        if 's' in plus:
            state['state'] = plus['s']
        if plus.get('c') is not None:
            state['context'] = context_of(plus['c'], state.get('context'))
        if plus.get('lc') is not None:
            state['last_changed'] = state['last_updated'] = moment(plus['lc'])
        elif plus.get('lu') is not None:
            state['last_updated'] = moment(plus['lu'])
        states[entity_id] = state
        touched.add(entity_id)
    return touched
