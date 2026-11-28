"""A light's effects page (app 0.2.83 / firmware 0.2.70): what the screen shows for a lamp with modes, such as a WLED.

Home Assistant is the source of every name and list here. The light's own `effect_list` is one row; the select and
number entities on the light's device (WLED: color palette, preset, playlist, speed, intensity) are the others, named
as Home Assistant names them in English (frontend/get_translations `entity`) with the icons its frontend shows. Nothing
about a brand is hardcoded: a lamp with only an effect list gets one row, a lamp without any gets no page.

The current values travel in the tile's state message (`x.rows`, `x.nums`); the lists themselves are asked for when a
picker opens (`esphome.screen_options` -> `op: options`), one page per message, so the screen holds no list while the
picker is closed and always shows what Home Assistant has at that moment.
"""
import json

import catalogue

# LightEntityFeature.EFFECT, from Home Assistant's source through the tile catalogue (catalogue/_ha.json).
EFFECT = catalogue.bits('light', 'EFFECT')
# Rows the effects page has room for: the effect plus three selects, and two numbers (a Guition shows them all).
SELECT_ROWS = 3
NUMBER_ROWS = 2
# Where these translation keys occur they come first, in this order; everything else follows by name. This is
# presentation only: the rows themselves still come from the device.
PREFERRED_SELECTS = ('color_palette', 'preset', 'playlist')
PREFERRED_NUMBERS = ('speed', 'intensity')
# A message to the screen is at most 4096 bytes; the names of one page stay well under it.
PAGE_BYTES = 3400
NAME_LIMIT = 48
OPTIONS_EVENT = 'esphome.screen_options'


def supports_effects(attrs):
    """Whether the light offers effects: Home Assistant's EFFECT feature and a list to choose from."""
    features = (attrs or {}).get('supported_features')
    return isinstance(features, int) and bool(features & EFFECT) and isinstance((attrs or {}).get('effect_list'), list)


def effect_options(attrs):
    """The light's effects as the picker lists them: alphabetically, with "Solid" (WLED's plain colour) first."""
    names = [str(v) for v in (attrs or {}).get('effect_list') or [] if isinstance(v, (str, int, float)) and not isinstance(v, bool)]
    names = [n for n in names if n.strip()]
    solid = [n for n in names if n.strip().lower() == 'solid']
    rest = sorted((n for n in names if n.strip().lower() != 'solid'), key=lambda n: (n.casefold(), n))
    return solid[:1] + rest


def _numeric(options):
    """A select whose every option is a bare number (WLED's live override: 0, 1, 2) is a technical setting, not a mode."""
    return all(isinstance(o, str) and o.strip().lstrip('-').isdigit() for o in options)


def _qualifies(item, states):
    """A select or number of the device the page can show: enabled, not hidden, not diagnostic."""
    eid = item.get('entity_id') or ''
    if item.get('disabled_by') or item.get('hidden_by') or item.get('entity_category') == 'diagnostic':
        return False
    state = states.get(eid)
    if not isinstance(state, dict):
        return False
    attrs = state.get('attributes') or {}
    if eid.startswith('select.'):
        options = attrs.get('options')
        return isinstance(options, list) and bool(options) and all(isinstance(o, str) for o in options) and not _numeric(options)
    if eid.startswith('number.'):
        try:
            return float(attrs.get('min')) < float(attrs.get('max'))
        except (TypeError, ValueError):
            return False
    return False


def _order(items, preferred, names):
    def rank(item):
        key = item.get('translation_key') or ''
        return (preferred.index(key) if key in preferred else len(preferred), names[item['entity_id']].casefold())
    return sorted(items, key=rank)


def entity_name(eid, entry, states, words):
    """Home Assistant's English name of a device's entity: its integration's translation for the entity's key
    (component.wled.entity.select.color_palette.name = "Color palette"), else the name Home Assistant shows, without the
    device's name in front of it ("VUELTA Kleurenpalet" is "Kleurenpalet")."""
    entry = entry if isinstance(entry, dict) else {}
    domain = eid.split('.', 1)[0]
    if isinstance(words, dict) and entry.get('platform') and entry.get('translation_key'):
        word = words.get(f"component.{entry['platform']}.entity.{domain}.{entry['translation_key']}.name")
        if isinstance(word, str) and word and '{' not in word:
            return word
    name = entry.get('name') or entry.get('original_name') or (states.get(eid, {}).get('attributes') or {}).get('friendly_name') or eid
    return str(name)


def strip_device_name(name, device_name):
    """"VUELTA Kleurenpalet" without the device's name, as Home Assistant's device page shows it."""
    if isinstance(device_name, str) and device_name and name.lower().startswith(device_name.lower() + ' '):
        return name[len(device_name) + 1:] or name
    return name


def siblings(entity, device, states):
    """The select and number entities on the light's device that its effects page shows, in page order."""
    selects, numbers = [], []
    for item in device or ():
        eid = item.get('entity_id') or ''
        if eid == entity or not _qualifies(item, states):
            continue
        (selects if eid.startswith('select.') else numbers).append(item)
    return selects, numbers


def related(entity, device, states):
    """Entity ids the light's card reads besides its own, for the manager's watch list."""
    selects, numbers = siblings(entity, device, states)
    return tuple(item['entity_id'] for item in selects + numbers)


def rows(entity, device, states, entries=None, words=None, icon_of=None, device_name=None):
    """The `rows` (selects) and `nums` (numbers) of the light's effects page for the tile's extra block, or {}.

    `entries` is the registry by entity id (names and translation keys), `words` Home Assistant's English entity
    translations, `icon_of(eid, state, attributes, entry)` the codepoint of the icon Home Assistant shows, or None."""
    selects, numbers = siblings(entity, device, states)
    entries = entries or {}
    names = {}
    for item in selects + numbers:
        eid = item['entity_id']
        entry = entries.get(eid, item)
        names[eid] = strip_device_name(entity_name(eid, entry, states, words), device_name)
    result = {}
    found = []
    for item in _order(selects, PREFERRED_SELECTS, names)[:SELECT_ROWS]:
        eid = item['entity_id']
        state = states[eid]
        attrs = state.get('attributes') or {}
        row = {'e': eid, 'n': _short(names[eid], 32), 's': _short(state.get('state') if isinstance(state.get('state'), str) else '', NAME_LIMIT),
               'c': len(attrs.get('options') or [])}
        icon = icon_of(eid, state.get('state'), attrs, entries.get(eid, item)) if icon_of else None
        if icon:
            row['i'] = icon
        found.append(row)
    if found:
        result['rows'] = found
    found = []
    for item in _order(numbers, PREFERRED_NUMBERS, names)[:NUMBER_ROWS]:
        eid = item['entity_id']
        state = states[eid]
        attrs = state.get('attributes') or {}
        row = {'e': eid, 'n': _short(names[eid], 32), 'lo': _number(attrs.get('min'), 0), 'hi': _number(attrs.get('max'), 100),
               'st': _number(attrs.get('step'), 1)}
        value = _number(state.get('state'), None)
        if value is not None:
            row['v'] = value
        icon = icon_of(eid, state.get('state'), attrs, entries.get(eid, item)) if icon_of else None
        if icon:
            row['i'] = icon
        found.append(row)
    if found:
        result['nums'] = found
    return result


def options_for(entity, states, layout_entities=(), device_of=None):
    """The names a picker lists for `entity`, or None when the screen may not ask for them: a light on the layout (its
    effects) or a select on the device of such a light (its options). `device_of(light)` gives that device's entries."""
    state = states.get(entity)
    if not isinstance(state, dict):
        return None
    attrs = state.get('attributes') or {}
    if entity.startswith('light.'):
        return effect_options(attrs) if entity in layout_entities and supports_effects(attrs) else None
    if entity.startswith('select.'):
        for light in layout_entities:
            if light.startswith('light.') and device_of and entity in related(light, device_of(light), states):
                options = attrs.get('options')
                return [str(o) for o in options if isinstance(o, str)] if isinstance(options, list) else None
    return None


def pages(names):
    """The names cut into pages whose message stays under the screen's limit (216 WLED effects are one page)."""
    result, page, size = [], [], 0
    for name in names:
        name = _short(name, NAME_LIMIT)
        cost = len(json.dumps(name, ensure_ascii=False).encode()) + 1
        if page and size + cost > PAGE_BYTES:
            result.append(page)
            page, size = [], 0
        page.append(name)
        size += cost
    if page or not result:
        result.append(page)
    return result


def message(entity, page, all_pages):
    """One page of a picker's names, as the screen parses it (`op: options`)."""
    page = max(0, min(int(page), len(all_pages) - 1))
    return {'v': 1, 'op': 'options', 'e': entity, 'i': page, 'n': len(all_pages), 'o': all_pages[page]}


def _short(value, limit):
    value = str(value if value is not None else '')
    return value if len(value) <= limit else value[:limit - 1] + '…'


def _number(value, fallback):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number != number or number in (float('inf'), float('-inf')):
        return fallback
    return int(number) if number.is_integer() else round(number, 3)


def choices(entity, device, states, entries=None, words=None, device_name=None):
    """What a light's presets may set beside its colour (the editor's preset popover): its effects, and the rows of its
    effects page with every choice they have: a select's options, a number's range. A light group has no device, so its
    effects alone. The rows in the page's order, all of them (the page shows the first few)."""
    attrs = (states.get(entity) or {}).get('attributes') or {}
    selects, numbers = siblings(entity, device, states)
    entries = entries or {}
    names = {}
    for item in selects + numbers:
        names[item['entity_id']] = strip_device_name(entity_name(item['entity_id'], entries.get(item['entity_id'], item), states, words), device_name)
    rows = []
    for item in _order(selects, PREFERRED_SELECTS, names) + _order(numbers, PREFERRED_NUMBERS, names):
        eid = item['entity_id']
        entry = entries.get(eid, item)
        state = states[eid]
        a = state.get('attributes') or {}
        row = {'e': eid, 'n': names[eid], 'key': entry.get('translation_key') or '', 'kind': eid.split('.', 1)[0]}
        if eid.startswith('select.'):
            row.update(options=[str(o) for o in a.get('options') or [] if isinstance(o, str)], value=state.get('state'))
        else:
            row.update(min=_number(a.get('min'), 0), max=_number(a.get('max'), 100), step=_number(a.get('step'), 1),
                       value=_number(state.get('state'), None))
        rows.append(row)
    return {'effects': effect_options(attrs) if supports_effects(attrs) else [], 'rows': rows}
